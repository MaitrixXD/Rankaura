"""
Lightweight similarity engine using TF-IDF and character/token n-gram overlap.
Zero model download required. Default similarity engine.
"""

from __future__ import annotations

import math
from collections import Counter
from typing import List, Sequence

from keyword_analysis.utils.normalizer import normalize, tokenize


class LightweightSimilarity:
    """
    Computes lexical and token overlap similarity between candidate strings and the seed.
    Combines word-level Jaccard/overlap with sub-word character n-gram cosine overlap
    so it works gracefully even for short phrases without pre-trained embeddings.
    """

    def __init__(self):
        pass

    @staticmethod
    def _char_ngrams(text: str, n: int = 3) -> Counter:
        norm = f" {normalize(text)} "
        if len(norm) < n:
            return Counter([norm])
        return Counter(norm[i : i + n] for i in range(len(norm) - n + 1))

    @classmethod
    def char_ngram_cosine(cls, s1: str, s2: str, n: int = 3) -> float:
        c1 = cls._char_ngrams(s1, n)
        c2 = cls._char_ngrams(s2, n)
        all_keys = set(c1.keys()) | set(c2.keys())
        dot = sum(c1[k] * c2[k] for k in all_keys)
        norm1 = math.sqrt(sum(v * v for v in c1.values()))
        norm2 = math.sqrt(sum(v * v for v in c2.values()))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    @classmethod
    def token_overlap(cls, s1: str, s2: str) -> float:
        t1 = set(tokenize(normalize(s1)))
        t2 = set(tokenize(normalize(s2)))
        if not t1 or not t2:
            return 0.0
        # Overlap relative to the smaller set (containment) plus Jaccard
        intersection = t1 & t2
        containment = len(intersection) / min(len(t1), len(t2))
        jaccard = len(intersection) / len(t1 | t2)
        return 0.7 * containment + 0.3 * jaccard

    def compute_similarity(self, candidate: str, seed: str) -> float:
        """
        Compute similarity score between candidate and seed topic [0.0 - 1.0].
        Blends character n-gram cosine (captures roots & stems) with token overlap.
        """
        c_sim = self.char_ngram_cosine(candidate, seed, n=3)
        t_sim = self.token_overlap(candidate, seed)
        # Weighted blend
        score = 0.55 * c_sim + 0.45 * t_sim
        return round(min(max(score, 0.0), 1.0), 4)

    def compute_batch_similarity(self, candidates: Sequence[str], seed: str) -> List[float]:
        return [self.compute_similarity(c, seed) for c in candidates]
