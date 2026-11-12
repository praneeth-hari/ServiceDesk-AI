from datetime import datetime, timezone
import logging
import time
from typing import Any, Optional, Sequence
import numpy as np
import sqlalchemy as sa
from sqlalchemy.orm import Session

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
    Generate and upsert embedding for the given ticket using the active embedder.
    Catches all exceptions, logs a warning, and carries on so ticket operations never fail.
    """
    try:
        active_embedder = embedder or get_embedder()
        text = get_text_to_embed(ticket.title, ticket.description)
        vectors = active_embedder.embed([text])
        if not vectors:
            return

        vec = vectors[0].astype(np.float32)
        existing = db.get(TicketEmbedding, ticket.id)
        now = datetime.now(timezone.utc)

        if existing:
            existing.model_name = active_embedder.name
            existing.dim = int(vec.shape[0])
            existing.vector = vec.tobytes()
            existing.updated_at = now
        else:
            emb = TicketEmbedding.from_numpy(
                ticket_id=ticket.id,
                model_name=active_embedder.name,
                vec=vec,
                updated_at=now,
            )
            db.add(emb)
        db.flush()
    except Exception as exc:
        logger.warning(
            "Failed to sync embedding for ticket %s: %s",
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
    - Limits candidate search to the most recent AI_MAX_CANDIDATES with matching model_name.
    - Privacy rule: Requesters only receive their own tickets. Agents and admins see all.
    - Excludes exclude_ticket_id if specified.
    """
    active_embedder = embedder or get_embedder()
    vectors = active_embedder.embed([text])
    if not vectors:
        return []
    query_vec = vectors[0]

    # Query embeddings with tickets
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
       - Similarity-weighted vote over top AI_KNN_K neighbours among resolved or closed tickets
         with similarity >= AI_MIN_SIMILARITY.
       - The vote uses all resolved/closed tickets (aggregated only).
       - The returned evidence list strictly respects privacy (requester sees only their own tickets).
    2. Duplicate Detection:
       - Open, in_progress, or waiting_on_requester tickets with similarity >= AI_DUPLICATE_THRESHOLD.
       - Privacy rule strictly applies: requesters only see their own potential duplicates.
    """
    active_embedder = embedder or get_embedder()
    text = get_text_to_embed(title, description)
    vectors = active_embedder.embed([text])
    if not vectors:
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
            "embedder": active_embedder.name,
            "method": "knn",
            "fallback_reason": ("No text to embed" if settings.AI_TRIAGE_MODE == "llm" else None),
        }
    query_vec = vectors[0]

    # Fetch candidate pool (up to AI_MAX_CANDIDATES) for active embedder
    stmt = (
        sa.select(TicketEmbedding, Ticket)
        .join(Ticket, TicketEmbedding.ticket_id == Ticket.id)
        .where(TicketEmbedding.model_name == active_embedder.name)
        .order_by(Ticket.id.desc())
        .limit(settings.AI_MAX_CANDIDATES)
    )
    records = db.execute(stmt).all()
    all_scored = _compute_cosine_similarities(query_vec, records)

    # 1. kNN Suggestion Candidates: resolved or closed tickets
    resolved_candidates = [
        c
        for c in all_scored
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

    # Evidence list: filter by user privacy
    if current_user.role == UserRole.REQUESTER:
        evidence = [c for c in top_neighbours if c["requester_id"] == current_user.id]
    else:
        evidence = top_neighbours

    # 2. Duplicate Detection: open, in_progress, or waiting_on_requester
    unresolved_statuses = (
        TicketStatus.OPEN,
        TicketStatus.IN_PROGRESS,
        TicketStatus.WAITING_ON_REQUESTER,
    )
    duplicate_candidates = [
        c
        for c in all_scored
        if c["status"] in unresolved_statuses
        and c["similarity"] >= settings.AI_DUPLICATE_THRESHOLD
    ]
    duplicate_candidates.sort(key=lambda c: c["similarity"], reverse=True)

    # Filter duplicates by privacy
    if current_user.role == UserRole.REQUESTER:
        duplicates = [c for c in duplicate_candidates if c["requester_id"] == current_user.id]
    else:
        duplicates = duplicate_candidates

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
                rag_examples = resolved_candidates[: settings.AI_LLM_EXAMPLES]

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
        "embedder": active_embedder.name,
        "method": method,
        "fallback_reason": fallback_reason,
    }
