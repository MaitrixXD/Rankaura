"""
Text normalizer and deduplication helpers.

All keyword strings pass through normalize() before any comparison,
enrichment, or storage. This ensures consistent dedup and matching.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Set


def normalize(text: str) -> str:
    """
    Canonical form for a keyword phrase:
      1. Unicode NFKC normalization
      2. Lowercase
      3. Strip leading/trailing whitespace
      4. Remove punctuation except hyphens (preserves "how-to" etc.)
      5. Collapse multiple whitespace to single space
    """
    text = unicodedata.normalize("NFKC", text)
    text = text.lower().strip()
    # Remove punctuation except hyphens and apostrophes
    text = re.sub(r"[^\w\s\-']", "", text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def deduplicate(phrases: List[str]) -> List[str]:
    """
    Remove exact duplicates after normalization, preserving insertion order.
    """
    seen: Set[str] = set()
    result: List[str] = []
    for phrase in phrases:
        normed = normalize(phrase)
        if normed and normed not in seen:
            seen.add(normed)
            result.append(normed)
    return result


def tokenize(phrase: str) -> List[str]:
    """Split a normalized phrase into word tokens."""
    return phrase.split()


def jaccard_similarity(a: str, b: str) -> float:
    """
    Token-level Jaccard similarity between two phrases.
    Used for near-duplicate detection in the Filter stage.
    """
    tokens_a = set(tokenize(normalize(a)))
    tokens_b = set(tokenize(normalize(b)))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def extract_ngrams(text: str, min_n: int = 2, max_n: int = 5) -> List[str]:
    """
    Extract contiguous n-grams from a text string.
    Used for phrase extraction from customer-language sources
    (e.g. Reddit/StackExchange question titles).
    """
    tokens = tokenize(normalize(text))
    ngrams: List[str] = []
    for n in range(min_n, min(max_n + 1, len(tokens) + 1)):
        for i in range(len(tokens) - n + 1):
            ngrams.append(" ".join(tokens[i : i + n]))
    return ngrams
