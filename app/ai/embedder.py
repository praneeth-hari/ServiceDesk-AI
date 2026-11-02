import logging
from typing import Optional, Protocol, runtime_checkable
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
    else:
        raise ValueError(
            f"Unknown embedder name '{target_name}'. Allowed: 'hashing', 'hashing-v2', 'sbert'"
        )

    _EMBEDDER_CACHE[target_name] = embedder
    return embedder
