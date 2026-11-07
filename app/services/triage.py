from datetime import datetime, timezone
import logging
import time
from typing import Any, Optional, Sequence
import numpy as np
import sqlalchemy as sa
from sqlalchemy.orm import Session, joinedload

from app.ai.embedder import Embedder, get_embedder, get_text_to_embed
from app.ai.injection_guard import inspect_ticket
from app.ai.llm_triage import triage_with_llm
from app.core.config import settings
from app.models.embedding import TicketEmbedding
from app.models.enums import TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.llm_triage_log import LLMTriageLog
from app.models.ticket import Ticket
from app.models.user import User

logger = logging.getLogger("helpdesk_api")


def map_fallback_reason(reason: Optional[str]) -> Optional[str]:
    """
    Map internal triage error messages to one of the 5 canonical telemetry fallback reasons:
    - possible_prompt_injection
    - timeout
    - unreachable
    - invalid_output
    - other
    """
    if not reason:
        return None
    r = reason.strip().lower()
    if "injection" in r:
        return "possible_prompt_injection"
    if "timed out" in r or "timeout" in r:
        return "timeout"
    if (
        "unreachable" in r
        or "not reachable" in r
        or "connection error" in r
        or "connection refused" in r
        or "not found" in r
        or "http error" in r
    ):
        return "unreachable"
    if (
        "invalid_output" in r
        or "invalid llm output" in r
        or "invalid output" in r
        or "json" in r
        or "validation" in r
        or "parse" in r
    ):
        return "invalid_output"
    return "other"


def _log_llm_triage_telemetry(
    db: Session,
    method: str,
    latency_ms: int,
    fallback_reason: Optional[str],
) -> None:
    """
    Log operational telemetry for an LLM triage attempt.
    Contains timing and outcome only; strictly NO ticket text or user identifiers.
    Uses a nested savepoint so:
    (a) a failed log insert never rolls back the caller's pending changes, and
    (b) a successful log write never commits the caller's transaction.
    """
    try:
        bind = db.get_bind() if hasattr(db, "get_bind") else getattr(db, "bind", None)
        dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
        now_dt = datetime.now(timezone.utc)
        created_dt = now_dt.replace(tzinfo=None) if dialect_name == "sqlite" else now_dt

        with db.begin_nested():
            entry = LLMTriageLog(
                created_at=created_dt,
                method=method,
                latency_ms=max(0, int(latency_ms)),
                fallback_reason=fallback_reason,
            )
            db.add(entry)
            db.flush()
    except Exception as exc:
        logger.warning("Failed to log LLM triage telemetry: %s", exc)


def predict_knn(
    candidates: Sequence[dict[str, Any]],
    k: int,
    min_similarity: float,
) -> tuple[Optional[TicketCategory], Optional[TicketPriority], float]:
    """
    Predict category and priority via similarity-weighted k-Nearest Neighbours (kNN).

    Mathematical formulation:
    1. Filter candidate neighbours with cosine similarity s_i >= min_similarity.
    2. Sort descending by similarity and take the top k candidates.
    3. For each label candidate c in categories and priorities, compute similarity-weighted vote:
       Vote(c) = sum_{i in top_k: label_i = c} s_i
    4. Winning label c* = argmax_c Vote(c).
    5. Confidence is the proportion of winning category weight over total neighbour weight:
       Confidence = Vote(c*) / sum_{i in top_k} s_i

    Returns:
        (winning_category, winning_priority, confidence)
        If no candidates meet min_similarity, returns (None, None, 0.0).
    """
    valid_candidates = [c for c in candidates if float(c.get("similarity", 0.0)) >= min_similarity]
    if not valid_candidates:
        return None, None, 0.0

    valid_candidates.sort(key=lambda c: float(c.get("similarity", 0.0)), reverse=True)
    top_k = valid_candidates[:k]

    category_weights: dict[TicketCategory, float] = {}
    priority_weights: dict[TicketPriority, float] = {}
    total_weight = 0.0

    for cand in top_k:
        weight = float(cand.get("similarity", 0.0))
        total_weight += weight

        cat = cand.get("category")
        if cat is not None:
            cat_enum = TicketCategory(cat) if isinstance(cat, str) else cat
            category_weights[cat_enum] = category_weights.get(cat_enum, 0.0) + weight

        prio = cand.get("priority")
        if prio is not None:
            prio_enum = TicketPriority(prio) if isinstance(prio, str) else prio
            priority_weights[prio_enum] = priority_weights.get(prio_enum, 0.0) + weight

    if total_weight <= 0.0 or not category_weights:
        return None, None, 0.0

    winning_category = max(category_weights.items(), key=lambda item: item[1])[0]
    winning_priority = (
        max(priority_weights.items(), key=lambda item: item[1])[0] if priority_weights else None
    )

    winning_cat_weight = category_weights[winning_category]
    confidence = float(winning_cat_weight / total_weight)

    return winning_category, winning_priority, round(confidence, 4)


def sync_ticket_embedding(
    db: Session,
    ticket: Ticket,
    embedder: Optional[Embedder] = None,
) -> None:
    """
    Generate and upsert embedding for the given ticket.
    - Always generates and stores the hashing-v2 vector.
    - If AI_EMBEDDER is nomic (or embedder passed is nomic), ALSO generates and stores
      the nomic vector.
    - Embeddings are computed BEFORE entering the database write section to ensure no
      external Ollama calls occur inside an open DB write transaction.
    - Clean upsert on composite primary key (ticket_id, model_name).
    - If nomic generation fails (Ollama unreachable, times out at 3.0s, or returns empty),
      logs a warning and continues so the hashing-v2 vector is always written and ticket
      operations never fail.
    """
    vectors_to_write: list[tuple[str, np.ndarray]] = []
    text = get_text_to_embed(ticket.title, ticket.description)
    if not text:
        return

    # 1. Always compute hashing-v2 vector
    try:
        hashing_embedder = get_embedder("hashing")
        h_vecs = hashing_embedder.embed([text])
        if h_vecs:
            vectors_to_write.append((hashing_embedder.name, h_vecs[0].astype(np.float32)))
    except Exception as exc:
        logger.warning(
            "Failed to compute hashing-v2 embedding for ticket %s: %s",
            getattr(ticket, "id", None),
            exc,
            exc_info=True,
        )

    # 2. Check if nomic is active or requested
    is_nomic = False
    nomic_embedder = None
    if embedder is not None and getattr(embedder, "name", "") == "nomic-embed-text":
        is_nomic = True
        nomic_embedder = embedder
    elif embedder is None and getattr(settings, "AI_EMBEDDER", "hashing") in ("nomic", "nomic-embed-text"):
        is_nomic = True
        try:
            nomic_embedder = get_embedder("nomic")
        except Exception as exc:
            logger.warning("Could not initialize nomic embedder: %s", exc)

    if is_nomic and nomic_embedder is not None:
        try:
            if hasattr(nomic_embedder, "embed_documents"):
                n_vecs = nomic_embedder.embed_documents([text])
            else:
                n_vecs = nomic_embedder.embed([text])
            if n_vecs:
                vectors_to_write.append((nomic_embedder.name, n_vecs[0].astype(np.float32)))
            else:
                logger.warning("Nomic embedder returned empty vectors for ticket %s", getattr(ticket, "id", None))
        except Exception as exc:
            logger.warning(
                "Failed to compute nomic embedding for ticket %s: %s",
                getattr(ticket, "id", None),
                exc,
            )

    # 3. If an explicit custom embedder was passed (e.g. sbert) that is neither hashing nor nomic
    if embedder is not None and getattr(embedder, "name", "") not in ("hashing-v2", "nomic-embed-text"):
        try:
            c_vecs = embedder.embed([text])
            if c_vecs:
                vectors_to_write.append((embedder.name, c_vecs[0].astype(np.float32)))
        except Exception as exc:
            logger.warning(
                "Failed to compute %s embedding for ticket %s: %s",
                getattr(embedder, "name", "custom"),
                getattr(ticket, "id", None),
                exc,
            )

    if not vectors_to_write:
        return

    # Write to database (clean upsert on (ticket_id, model_name))
    try:
        now = datetime.now(timezone.utc)
        for model_name, vec in vectors_to_write:
            existing = db.get(TicketEmbedding, (ticket.id, model_name))
            if existing:
                existing.dim = int(vec.shape[0])
                existing.vector = vec.tobytes()
                existing.updated_at = now
            else:
                emb = TicketEmbedding.from_numpy(
                    ticket_id=ticket.id,
                    model_name=model_name,
                    vec=vec,
                    updated_at=now,
                )
                db.add(emb)
        db.flush()
    except Exception as exc:
        logger.warning(
            "Failed to save embeddings for ticket %s: %s",
            getattr(ticket, "id", None),
            exc,
            exc_info=True,
        )


def _compute_cosine_similarities(
    query_vector: np.ndarray,
    candidate_records: Sequence[tuple[TicketEmbedding, Ticket]],
) -> list[dict[str, Any]]:
    """
    Compute cosine similarities between a query vector and stored ticket embeddings.

    Mathematical formulation:
    cos(theta) = (u . v) / (||u|| * ||v||)
    Because all vectors produced by the embedders are normalized to unit length (||u|| = ||v|| = 1),
    cosine similarity simplifies to the Euclidean dot product: u . v.
    """
    if not candidate_records:
        return []

    # Stack stored vectors into a 2D matrix (N, dim)
    vectors = []
    metadata = []
    for emb, ticket in candidate_records:
        vec = emb.get_numpy_vector()
        if vec.shape[0] != query_vector.shape[0]:
            logger.warning(
                "Skipping embedding for ticket %s: vector dim %d does not match query dim %d",
                getattr(ticket, "id", None),
                vec.shape[0],
                query_vector.shape[0],
            )
            continue
        vectors.append(vec)
        metadata.append(ticket)

    if not vectors:
        return []
    matrix = np.vstack(vectors).astype(np.float32)
    # Dot product of normalized vectors
    sims = np.dot(matrix, query_vector.astype(np.float32))

    results = []
    for i, ticket in enumerate(metadata):
        sim = float(sims[i])
        # Clip numerical inaccuracies to [-1.0, 1.0]
        sim = max(-1.0, min(1.0, sim))
        results.append(
            {
                "id": ticket.id,
                "title": ticket.title,
                "description": ticket.description,
                "status": ticket.status,
                "category": ticket.category,
                "priority": ticket.priority,
                "created_at": ticket.created_at,
                "requester_id": ticket.requester_id,
                "similarity": round(sim, 4),
            }
        )
    return results


def find_similar(
    db: Session,
    text: str,
    current_user: User,
    exclude_ticket_id: Optional[int] = None,
    limit: int = 5,
    embedder: Optional[Embedder] = None,
) -> list[dict[str, Any]]:
    """
    Find stored tickets most similar to the given text using cosine similarity.
    - Default to hashing-v2. If someone explicitly passes an embedder, use that embedder
      and its matching model_name rows.
    - Limits candidate search to the most recent AI_MAX_CANDIDATES with matching model_name.
    - Privacy rule: Requesters only receive their own tickets. Agents and admins see all.
    - Excludes exclude_ticket_id if specified.
    """
    active_embedder = embedder if embedder is not None else get_embedder("hashing")
    if hasattr(active_embedder, "embed_query"):
        vectors = active_embedder.embed_query([text])
    else:
        vectors = active_embedder.embed([text])
    if not vectors:
        return []
    query_vec = vectors[0]

    # Query embeddings with tickets matching the active embedder's model_name
    stmt = (
        sa.select(TicketEmbedding, Ticket)
        .join(Ticket, TicketEmbedding.ticket_id == Ticket.id)
        .where(TicketEmbedding.model_name == active_embedder.name)
        .order_by(Ticket.id.desc())
        .limit(settings.AI_MAX_CANDIDATES)
    )

    if exclude_ticket_id is not None:
        stmt = stmt.where(Ticket.id != exclude_ticket_id)

    # Privacy filtering at the SQL level for find_similar
    if current_user.role == UserRole.REQUESTER:
        stmt = stmt.where(Ticket.requester_id == current_user.id)

    records = db.execute(stmt).all()
    results = _compute_cosine_similarities(query_vec, records)
    results.sort(key=lambda r: r["similarity"], reverse=True)
    return results[:limit]


def suggest(
    db: Session,
    title: str,
    description: str,
    current_user: User,
    embedder: Optional[Embedder] = None,
    log_telemetry: bool = True,
) -> dict[str, Any]:
    """
    Advisory AI triage suggestions and duplicate detection.

    1. Category & Priority Suggestion:
       - Uses nomic-embed-text if AI_EMBEDDER == "nomic" (or embedder passed is nomic) and
         nomic index is non-empty and Ollama is reachable within timeout (3.0s).
       - Falls back to hashing-v2 if nomic has zero vectors in DB (embedder_fallback_reason="nomic_no_embeddings")
         or if Ollama is unreachable/times out (embedder_fallback_reason="nomic_unreachable").
       - Predicts via similarity-weighted vote over top AI_KNN_K neighbours among resolved or closed
         tickets with similarity >= AI_MIN_SIMILARITY in the active embedder's space.
    2. Duplicate Detection:
       - Always evaluated in the hashing-v2 space with hashing-v2 query vector.
       - Open, in_progress, or waiting_on_requester tickets with similarity >= AI_DUPLICATE_THRESHOLD.
    3. LLM-Assisted Triage:
       - RAG examples stay on the hashing-v2 space.
    """
    requested_embedder = embedder or get_embedder()
    is_nomic_requested = (requested_embedder.name == "nomic-embed-text") or (
        embedder is None and getattr(settings, "AI_EMBEDDER", "hashing") in ("nomic", "nomic-embed-text")
    )

    text = get_text_to_embed(title, description)
    if not text:
        if settings.AI_TRIAGE_MODE == "llm" and log_telemetry:
            _log_llm_triage_telemetry(
                db=db,
                method="knn",
                latency_ms=0,
                fallback_reason="other",
            )
        return {
            "suggested_category": None,
            "suggested_priority": None,
            "confidence": 0.0,
            "evidence": [],
            "possible_duplicates": [],
            "embedder": requested_embedder.name,
            "embedder_fallback_reason": None,
            "method": "knn",
            "fallback_reason": ("No text to embed" if settings.AI_TRIAGE_MODE == "llm" else None),
        }

    # Hashing space is always computed for duplicate detection, LLM RAG examples, and kNN fallback
    hashing_embedder = get_embedder("hashing")
    hashing_vectors = hashing_embedder.embed([text])
    hashing_query_vec = hashing_vectors[0] if hashing_vectors else None

    hashing_stmt = (
        sa.select(TicketEmbedding, Ticket)
        .join(Ticket, TicketEmbedding.ticket_id == Ticket.id)
        .where(TicketEmbedding.model_name == "hashing-v2")
        .order_by(Ticket.id.desc())
        .limit(settings.AI_MAX_CANDIDATES)
    )
    hashing_records = db.execute(hashing_stmt).all()
    hashing_scored = (
        _compute_cosine_similarities(hashing_query_vec, hashing_records)
        if hashing_query_vec is not None
        else []
    )

    embedder_fallback_reason: Optional[str] = None
    knn_scored = hashing_scored
    active_embedder_name = "hashing-v2"

    if is_nomic_requested:
        hashing_count = db.scalar(
            sa.select(sa.func.count(TicketEmbedding.ticket_id)).where(TicketEmbedding.model_name == "hashing-v2")
        ) or 0
        nomic_count = db.scalar(
            sa.select(sa.func.count(TicketEmbedding.ticket_id)).where(TicketEmbedding.model_name == "nomic-embed-text")
        ) or 0

        if nomic_count == 0:
            logger.warning(
                "No nomic-embed-text embeddings found in database (%d hashing exist); falling back to hashing-v2",
                hashing_count,
            )
            embedder_fallback_reason = "nomic_no_embeddings"
            active_embedder_name = "hashing-v2"
            knn_scored = hashing_scored
        else:
            if nomic_count < hashing_count:
                logger.warning(
                    "Incomplete nomic embedding index: %d nomic vectors vs %d hashing vectors",
                    nomic_count,
                    hashing_count,
                )
            try:
                nomic_embedder = (
                    requested_embedder
                    if requested_embedder.name == "nomic-embed-text"
                    else get_embedder("nomic")
                )
                if hasattr(nomic_embedder, "embed_query"):
                    n_vectors = nomic_embedder.embed_query([text])
                else:
                    n_vectors = nomic_embedder.embed([text])
                if not n_vectors:
                    raise RuntimeError("Empty vector returned by nomic embedder")
                nomic_query_vec = n_vectors[0]

                nomic_stmt = (
                    sa.select(TicketEmbedding, Ticket)
                    .join(Ticket, TicketEmbedding.ticket_id == Ticket.id)
                    .where(TicketEmbedding.model_name == "nomic-embed-text")
                    .order_by(Ticket.id.desc())
                    .limit(settings.AI_MAX_CANDIDATES)
                )
                nomic_records = db.execute(nomic_stmt).all()
                knn_scored = _compute_cosine_similarities(nomic_query_vec, nomic_records)
                active_embedder_name = "nomic-embed-text"
                embedder_fallback_reason = None
            except Exception as exc:
                logger.warning(
                    "Nomic embedder failed (%s); falling back to hashing-v2",
                    exc,
                )
                embedder_fallback_reason = "nomic_unreachable"
                active_embedder_name = "hashing-v2"
                knn_scored = hashing_scored
    elif requested_embedder.name != "hashing-v2":
        custom_vectors = requested_embedder.embed([text])
        if custom_vectors:
            c_stmt = (
                sa.select(TicketEmbedding, Ticket)
                .join(Ticket, TicketEmbedding.ticket_id == Ticket.id)
                .where(TicketEmbedding.model_name == requested_embedder.name)
                .order_by(Ticket.id.desc())
                .limit(settings.AI_MAX_CANDIDATES)
            )
            c_records = db.execute(c_stmt).all()
            knn_scored = _compute_cosine_similarities(custom_vectors[0], c_records)
            active_embedder_name = requested_embedder.name

    # 1. kNN Suggestion Candidates: resolved or closed tickets
    resolved_candidates = [
        c
        for c in knn_scored
        if c["status"] in (TicketStatus.RESOLVED, TicketStatus.CLOSED)
        and c["similarity"] >= settings.AI_MIN_SIMILARITY
    ]
    resolved_candidates.sort(key=lambda c: c["similarity"], reverse=True)
    top_neighbours = resolved_candidates[: settings.AI_KNN_K]

    suggested_cat, suggested_prio, confidence = predict_knn(
        top_neighbours,
        k=settings.AI_KNN_K,
        min_similarity=settings.AI_MIN_SIMILARITY,
    )

    # Evidence list: filter by user privacy (filter before taking top K, not after)
    if current_user.role == UserRole.REQUESTER:
        requester_resolved = [
            c for c in resolved_candidates if c.get("requester_id") == current_user.id
        ]
        evidence = requester_resolved[: settings.AI_KNN_K]
    else:
        evidence = top_neighbours

    # 2. Duplicate Detection: open, in_progress, or waiting_on_requester
    # Defaults to hashing-v2 space (nomic never used for duplicates).
    # If a custom embedder (e.g. FakeEmbedder in tests) was explicitly passed, uses its scored pool.
    unresolved_statuses = (
        TicketStatus.OPEN,
        TicketStatus.IN_PROGRESS,
        TicketStatus.WAITING_ON_REQUESTER,
    )
    dup_pool = (
        knn_scored
        if requested_embedder.name not in ("hashing-v2", "nomic-embed-text")
        else hashing_scored
    )
    duplicate_candidates = [
        c
        for c in dup_pool
        if c["status"] in unresolved_statuses
        and c["similarity"] >= settings.AI_DUPLICATE_THRESHOLD
    ]
    duplicate_candidates.sort(key=lambda c: c["similarity"], reverse=True)

    # Filter duplicates by privacy and cap at 3
    if current_user.role == UserRole.REQUESTER:
        duplicates = [c for c in duplicate_candidates if c["requester_id"] == current_user.id]
    else:
        duplicates = duplicate_candidates
    duplicates = duplicates[:3]

    # 3. LLM-Assisted Triage (when AI_TRIAGE_MODE == "llm")
    method = "knn"
    fallback_reason: Optional[str] = None

    if settings.AI_TRIAGE_MODE == "llm":
        t0 = time.perf_counter()
        logged_latency_ms = 0
        logged_method = "knn"
        logged_fallback_reason: Optional[str] = None

        ticket_text = f"{title}\n{description}".strip()
        guard_res = inspect_ticket(ticket_text)
        if guard_res.is_injection:
            method = "knn"
            fallback_reason = "possible_prompt_injection"
            logged_method = "knn"
            logged_fallback_reason = "possible_prompt_injection"
            logged_latency_ms = int((time.perf_counter() - t0) * 1000)
            logger.warning(
                "Prompt injection detected by guard (rules: %s); falling back to kNN",
                guard_res.matched_rules,
            )
        else:
            try:
                # LLM RAG examples stay on the hashing-v2 candidate pool
                hashing_resolved = [
                    c
                    for c in hashing_scored
                    if c["status"] in (TicketStatus.RESOLVED, TicketStatus.CLOSED)
                    and c["similarity"] >= settings.AI_MIN_SIMILARITY
                ]
                hashing_resolved.sort(key=lambda c: c["similarity"], reverse=True)
                rag_examples = hashing_resolved[: settings.AI_LLM_EXAMPLES]

                llm_cat, llm_prio, latency_ms, error_reason = triage_with_llm(
                    ticket_text=ticket_text,
                    retrieved_examples=rag_examples,
                    model_name=settings.AI_LLM_MODEL,
                    base_url=settings.OLLAMA_BASE_URL,
                    timeout=settings.AI_LLM_TIMEOUT_SECONDS,
                )
                logged_latency_ms = int(latency_ms)

                if error_reason is not None or llm_cat is None or llm_prio is None:
                    method = "knn"
                    fallback_reason = error_reason or "LLM triage failed"
                    logged_method = "knn"
                    logged_fallback_reason = map_fallback_reason(fallback_reason)
                    logger.warning("LLM triage fallback to kNN: %s", fallback_reason)
                else:
                    suggested_cat = TicketCategory(llm_cat)
                    suggested_prio = TicketPriority(llm_prio)
                    confidence = None
                    method = "llm-rag"
                    fallback_reason = None
                    logged_method = "llm"
                    logged_fallback_reason = None
            except Exception as exc:
                method = "knn"
                fallback_reason = f"LLM error: {exc}"
                logged_method = "knn"
                logged_fallback_reason = "other"
                logged_latency_ms = int((time.perf_counter() - t0) * 1000)
                logger.warning("Unexpected error during LLM triage, falling back to kNN: %s", exc, exc_info=True)

        if log_telemetry:
            _log_llm_triage_telemetry(
                db=db,
                method=logged_method,
                latency_ms=logged_latency_ms,
                fallback_reason=logged_fallback_reason,
            )

    return {
        "suggested_category": suggested_cat,
        "suggested_priority": suggested_prio,
        "confidence": confidence,
        "evidence": evidence,
        "possible_duplicates": duplicates,
        "embedder": active_embedder_name,
        "embedder_fallback_reason": embedder_fallback_reason,
        "method": method,
        "fallback_reason": fallback_reason,
    }
