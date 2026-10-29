"""
Google Autocomplete adapter.

Uses the unofficial suggestqueries endpoint (client=firefox).
Rate-limited to ~0.4s between calls. Handles failures gracefully.
"""

from __future__ import annotations

from typing import List

import requests

from keyword_analysis.adapters.base import BaseAdapter, Candidate
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)

ENDPOINT = "https://suggestqueries.google.com/complete/search"


class GoogleAutocompleteAdapter(BaseAdapter):
    name = "google_autocomplete"

    def __init__(self, hl: str = "en", gl: str = "in", **kwargs):
        super().__init__(**kwargs)
        self._hl = hl
        self._gl = gl

    def _fetch_impl(self, query: str, **kwargs) -> List[Candidate]:
        distance = kwargs.get("distance", 1)
        resp = requests.get(
            ENDPOINT,
            params={"client": "firefox", "q": query, "hl": self._hl, "gl": self._gl},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        suggestions = resp.json()[1] if resp.json() else []
        return [
            Candidate(
                text=s, source=self.name, distance=distance,
                rank=i + 1, raw_query=query
            )
            for i, s in enumerate(suggestions)
            if isinstance(s, str) and s.strip()
        ]
