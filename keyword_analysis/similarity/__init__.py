"""Similarity engine factory and drift gate."""

from __future__ import annotations

from typing import Protocol, Sequence, List
from keyword_analysis.config import Config
from keyword_analysis.similarity.lightweight import LightweightSimilarity
from keyword_analysis.similarity.embeddings import EmbeddingSimilarity


class SimilarityEngine(Protocol):
    def compute_similarity(self, candidate: str, seed: str) -> float:
        ...

    def compute_batch_similarity(self, candidates: Sequence[str], seed: str) -> List[float]:
        ...


def get_similarity_engine(cfg: Config) -> SimilarityEngine:
    if cfg.similarity.method == "embeddings":
        return EmbeddingSimilarity(cfg.similarity.embedding_model)
    return LightweightSimilarity()
