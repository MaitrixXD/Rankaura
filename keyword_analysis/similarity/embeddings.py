"""
Embedding-based similarity engine using sentence-transformers (optional).
Falls back gracefully to LightweightSimilarity if sentence-transformers is not installed.
"""

from __future__ import annotations

from typing import List, Sequence
import numpy as np

from keyword_analysis.similarity.lightweight import LightweightSimilarity
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)


class EmbeddingSimilarity:
    """
    Computes dense vector semantic similarity using sentence-transformers.
    Loads model only when first instantiated.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._fallback = LightweightSimilarity()
        self._load_model()

    def _load_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            log.info("Loading sentence-transformers model '%s'...", self.model_name)
            self._model = SentenceTransformer(self.model_name)
            log.info("SentenceTransformer model loaded successfully.")
        except Exception as e:
            log.warning(
                "sentence-transformers not available or failed to load (%s). Falling back to lightweight lexical similarity.",
                e,
            )
            self._model = None

    @property
    def is_embedding_ready(self) -> bool:
        return self._model is not None

    def compute_similarity(self, candidate: str, seed: str) -> float:
        if self._model is None:
            return self._fallback.compute_similarity(candidate, seed)

        embeddings = self._model.encode([candidate, seed], normalize_embeddings=True)
        score = float(np.dot(embeddings[0], embeddings[1]))
        return round(float(np.clip(score, 0.0, 1.0)), 4)

    def compute_batch_similarity(self, candidates: Sequence[str], seed: str) -> List[float]:
        if not candidates:
            return []
        if self._model is None:
            return self._fallback.compute_batch_similarity(candidates, seed)

        all_texts = [seed] + list(candidates)
        embeddings = self._model.encode(all_texts, normalize_embeddings=True)
        seed_vec = embeddings[0]
        cand_vecs = embeddings[1:]
        scores = np.dot(cand_vecs, seed_vec)
        return [round(float(np.clip(s, 0.0, 1.0)), 4) for s in scores]

    def encode_corpus(self, texts: Sequence[str]) -> np.ndarray:
        """Return dense embeddings for clustering, or TF-IDF matrix if fallback."""
        if self._model is not None:
            return self._model.encode(list(texts), normalize_embeddings=True)
        from sklearn.feature_extraction.text import TfidfVectorizer
        tfidf = TfidfVectorizer(ngram_range=(1, 2))
        return tfidf.fit_transform(texts).toarray()
