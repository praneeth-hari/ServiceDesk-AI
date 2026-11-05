import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
from typing import Any, Optional, Protocol, runtime_checkable
import urllib.error
import urllib.request
import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from app.core.config import settings

logger = logging.getLogger("helpdesk_api")


@runtime_checkable
class Embedder(Protocol):
    """Protocol for text embedders returning unit-length float32 vectors."""

    @property
    def name(self) -> str:
        """Identifier of the embedding model."""
        ...

    @property
    def dim(self) -> int:
        """Dimensionality of the embedding vectors."""
        ...

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        """
        Embed a list of text strings into L2-normalized float32 numpy vectors.
        """
        ...


class HashingEmbedder:
    """
    Improved deterministic embedder using scikit-learn HashingVectorizer (model: 'hashing-v2').
    Combines:
    1. Word 1-2 grams with English stop words removed and sublinear term frequency.
    2. Character n-grams (analyzer 'char_wb', 3 to 5) with sublinear term frequency for
       morphological variation and typo resilience.
    L2-normalizes each component, stacks them with equal weight, and L2-normalizes the
    final vector to unit length (total dim = 2 * n_features = 4096).
    Fast, deterministic, requires no downloads or fitting.
    """

    def __init__(self, n_features: int = 2048) -> None:
        self._name = "hashing-v2"
        self._dim = n_features * 2
        self._word_vectorizer = HashingVectorizer(
            n_features=n_features,
            ngram_range=(1, 2),
            lowercase=True,
            stop_words="english",
            alternate_sign=False,
            norm=None,
        )
        self._char_vectorizer = HashingVectorizer(
            n_features=n_features,
            analyzer="char_wb",
            ngram_range=(3, 5),
            lowercase=True,
            alternate_sign=False,
            norm=None,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def dim(self) -> int:
        return self._dim

    def _transform_sublinear_l2(self, vectorizer: HashingVectorizer, texts: list[str]) -> np.ndarray:
        from sklearn.preprocessing import normalize

        X = vectorizer.transform(texts)
        if X.nnz > 0:
            # Sublinear TF scaling: 1 + log(tf) for tf > 0
            X.data = 1.0 + np.log(X.data)
        normalized = normalize(X, norm="l2").toarray().astype(np.float32)
        return normalized

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        if not texts:
            return []

        X_word = self._transform_sublinear_l2(self._word_vectorizer, texts)
        X_char = self._transform_sublinear_l2(self._char_vectorizer, texts)

        # Equal-weighted combination and final unit-length L2-normalization
        combined = np.hstack([X_word, X_char])
        norms = np.linalg.norm(combined, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        final_vectors = (combined / norms).astype(np.float32)

        return [row for row in final_vectors]


class SbertEmbedder:
    """
    Optional dense semantic embedder using sentence-transformers (all-MiniLM-L6-v2).
    Imported lazily; raises a helpful error if sentence-transformers is not installed.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._name = "sbert"
        self._model_name = model_name
        self._model = None
        self._dim = 384

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except (ImportError, ModuleNotFoundError) as exc:
                raise ImportError(
                    "sentence-transformers is not installed. Install requirements-ai.txt "
                    "(pip install -r requirements-ai.txt) to use the sbert embedder."
                ) from exc
            self._model = SentenceTransformer(self._model_name)
        return self._model

    @property
    def name(self) -> str:
        return self._name

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[np.ndarray]:
        if not texts:
            return []
        model = self._load_model()
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return [vec.astype(np.float32) for vec in vectors]


class OllamaEmbedder:
    """
    Dense semantic embedder using local Ollama (/api/embed) with nomic-embed-text.
    Supports configurable task prefixes and deterministic disk caching keyed by
    (model_name, model_digest, prefix, text_hash).
    """

    PREFIX_VARIANTS: dict[str, tuple[str, str]] = {
        "search": ("search_document: ", "search_query: "),
        "classification": ("classification: ", "classification: "),
        "clustering": ("clustering: ", "clustering: "),
        "none": ("", ""),
    }

    def __init__(
        self,
        model_name: str = "nomic-embed-text",
        base_url: Optional[str] = None,
        variant: str = "classification",
        doc_prefix: Optional[str] = None,
        query_prefix: Optional[str] = None,
        cache_dir: Optional[Path | str] = None,
        batch_size: int = 32,
        digest: Optional[str] = None,
        version: Optional[str] = None,
    ) -> None:
        self._name = "nomic-embed-text"
        self._model_name = model_name
        self._base_url = (base_url or getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
        self._variant = variant.lower() if variant else "none"
        if self._variant not in self.PREFIX_VARIANTS:
            raise ValueError(
                f"Unknown prefix variant '{variant}'. Supported variants: {list(self.PREFIX_VARIANTS.keys())}"
            )
        default_doc, default_query = self.PREFIX_VARIANTS[self._variant]
        self._doc_prefix = doc_prefix if doc_prefix is not None else default_doc
        self._query_prefix = query_prefix if query_prefix is not None else default_query
        self._batch_size = batch_size
        self._dim = 768
        self._digest = digest
        self._version = version
        self._cache_dir = Path(cache_dir) if cache_dir is not None else Path(".cache") / "embeddings"
        self._cache_db_path = self._cache_dir / "cache.sqlite3"
        self._db_initialized = False
        self.cache_hits: int = 0
        self.cache_misses: int = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def variant(self) -> str:
        return self._variant

    @property
    def doc_prefix(self) -> str:
        return self._doc_prefix

    @property
    def query_prefix(self) -> str:
        return self._query_prefix

    @property
    def digest(self) -> str:
        if self._digest is None:
            self._fetch_model_metadata()
        return self._digest or "unknown"

    @property
    def version(self) -> str:
        if self._version is None:
            self._fetch_model_metadata()
        return self._version or "unknown"

    def _fetch_model_metadata(self) -> None:
        try:
            req_v = urllib.request.Request(f"{self._base_url}/api/version")
            with urllib.request.urlopen(req_v, timeout=5) as resp:
                v_data = json.loads(resp.read().decode("utf-8"))
                self._version = v_data.get("version", "unknown")
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {self._base_url}. Ensure Ollama is running."
            ) from exc
        except Exception:
            self._version = "unknown"

        try:
            req_t = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req_t, timeout=5) as resp:
                t_data = json.loads(resp.read().decode("utf-8"))
                models = t_data.get("models", [])
                match = None
                for m in models:
                    m_name = m.get("name", "")
                    if m_name == self._model_name or m_name.startswith(f"{self._model_name}:"):
                        match = m
                        break
                if match:
                    self._digest = match.get("digest", "unknown")
                else:
                    avail = [m.get("name", "") for m in models]
                    raise RuntimeError(
                        f"Model '{self._model_name}' not found in Ollama at {self._base_url}. Available: {avail}"
                    )
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {self._base_url}. Ensure Ollama is running."
            ) from exc

    def _init_db(self) -> None:
        if not self._db_initialized:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self._cache_db_path) as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS embeddings (cache_key TEXT PRIMARY KEY, vector BLOB)"
                )
                conn.commit()
            self._db_initialized = True

    def compute_cache_key(self, prefix: str, text: str) -> str:
        """
        Compute deterministic cache key for text under model name, model digest, and prefix.
        Key = sha256(model_name:digest:prefix:sha256(text)).
        """
        text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        raw = f"{self._model_name}:{self.digest}:{prefix}:{text_hash}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def embed(self, texts: list[str], prefix: Optional[str] = None) -> list[np.ndarray]:
        if not texts:
            return []

        eff_prefix = prefix if prefix is not None else self._doc_prefix
        self._init_db()

        keys = [self.compute_cache_key(eff_prefix, t) for t in texts]
        results: list[Optional[np.ndarray]] = [None] * len(texts)
        missing_indices: list[int] = []

        # 1. Read hits from sqlite cache
        with sqlite3.connect(self._cache_db_path) as conn:
            cur = conn.cursor()
            found_map: dict[str, np.ndarray] = {}
            chunk_size = 500
            for i in range(0, len(keys), chunk_size):
                k_chunk = keys[i : i + chunk_size]
                chunk_ph = ",".join("?" for _ in k_chunk)
                cur.execute(
                    f"SELECT cache_key, vector FROM embeddings WHERE cache_key IN ({chunk_ph})",
                    k_chunk,
                )
                for k, blob in cur.fetchall():
                    found_map[k] = np.frombuffer(blob, dtype=np.float32)

        for i, (t, k) in enumerate(zip(texts, keys)):
            if k in found_map:
                results[i] = found_map[k]
                self.cache_hits += 1
            else:
                missing_indices.append(i)
                self.cache_misses += 1

        # 2. Fetch misses from Ollama
        if missing_indices:
            newly_cached: list[tuple[str, bytes]] = []
            for batch_start in range(0, len(missing_indices), self._batch_size):
                batch_idxs = missing_indices[batch_start : batch_start + self._batch_size]
                batch_inputs = [f"{eff_prefix}{texts[idx]}" for idx in batch_idxs]

                raw_vectors = self._call_ollama_embed(batch_inputs)
                if len(raw_vectors) != len(batch_inputs):
                    raise RuntimeError(
                        f"Expected {len(batch_inputs)} embeddings from Ollama, got {len(raw_vectors)}"
                    )

                for idx, raw_vec in zip(batch_idxs, raw_vectors):
                    vec = np.array(raw_vec, dtype=np.float32)
                    norm = float(np.linalg.norm(vec))
                    if norm > 0.0:
                        vec = (vec / norm).astype(np.float32)
                    else:
                        vec = np.zeros_like(vec, dtype=np.float32)
                    results[idx] = vec
                    newly_cached.append((keys[idx], vec.tobytes()))

            if newly_cached:
                with sqlite3.connect(self._cache_db_path) as conn:
                    conn.executemany("INSERT OR REPLACE INTO embeddings VALUES (?, ?)", newly_cached)
                    conn.commit()

        return [r for r in results if r is not None]

    def _call_ollama_embed(self, inputs: list[str]) -> list[list[float]]:
        payload = json.dumps({"model": self._model_name, "input": inputs}).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/api/embed",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("embeddings", [])
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise RuntimeError(
                    f"Model '{self._model_name}' not found in Ollama at {self._base_url}. Run `ollama pull {self._model_name}`."
                ) from exc
            raise RuntimeError(f"Ollama API HTTP error {exc.code}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Cannot reach Ollama at {self._base_url}. Ensure Ollama is running."
            ) from exc

    def embed_documents(self, texts: list[str]) -> list[np.ndarray]:
        """Embed stored tickets using the document prefix."""
        return self.embed(texts, prefix=self._doc_prefix)

    def embed_query(self, texts: list[str]) -> list[np.ndarray]:
        """Embed incoming query tickets using the query prefix."""
        return self.embed(texts, prefix=self._query_prefix)



def get_text_to_embed(title: str, description: str) -> str:
    """Format ticket title and description for embedding representation."""
    clean_title = (title or "").strip()
    clean_desc = (description or "").strip()
    if clean_title and clean_desc:
        return f"{clean_title}. {clean_desc}"
    return clean_title or clean_desc


_EMBEDDER_CACHE: dict[str, Embedder] = {}


def get_embedder(name: Optional[str] = None) -> Embedder:
    """
    Factory function returning the active or requested Embedder instance.
    Uses settings.AI_EMBEDDER by default.
    """
    target_name = (name or settings.AI_EMBEDDER).lower()
    if target_name in _EMBEDDER_CACHE:
        return _EMBEDDER_CACHE[target_name]

    if target_name in ("hashing", "hashing-v2"):
        embedder = HashingEmbedder()
    elif target_name == "sbert":
        embedder = SbertEmbedder()
    elif target_name in ("nomic", "nomic-embed-text", "ollama"):
        embedder = OllamaEmbedder()
    else:
        raise ValueError(
            f"Unknown embedder name '{target_name}'. Allowed: 'hashing', 'hashing-v2', 'sbert', 'nomic', 'nomic-embed-text'"
        )

    _EMBEDDER_CACHE[target_name] = embedder
    return embedder
