"""
Datamuse adapter — free, no API key needed.

Uses the `ml=` (means like) endpoint to find semantically related words.
Returns synonyms, near-meanings, and related concepts.
"""

from __future__ import annotations

from typing import List

import requests

from keyword_analysis.adapters.base import BaseAdapter, Candidate
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)

ENDPOINT = "https://api.datamuse.com/words"


class DatamuseAdapter(BaseAdapter):
    name = "datamuse"

    def __init__(self, max_results: int = 20, **kwargs):
        super().__init__(**kwargs)
        self._max_results = max_results

    def _fetch_impl(self, query: str, **kwargs) -> List[Candidate]:
        resp = requests.get(
            ENDPOINT,
            params={"ml": query, "max": self._max_results},
            timeout=10,
        )
        resp.raise_for_status()
        words = resp.json()
        return [
            Candidate(
                text=w["word"], source=self.name, distance=1,
                rank=i + 1, raw_query=query,
                metadata={"datamuse_score": w.get("score", 0)}
            )
            for i, w in enumerate(words)
            if w.get("word", "").strip()
        ]
