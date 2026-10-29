"""
YouTube Autocomplete adapter. Optional, off by default.
Captures video/how-to intent queries.
"""

from __future__ import annotations

from typing import List

import requests

from keyword_analysis.adapters.base import BaseAdapter, Candidate
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)

ENDPOINT = "https://suggestqueries.google.com/complete/search"


class YouTubeAutocompleteAdapter(BaseAdapter):
    name = "youtube_autocomplete"

    def __init__(self, hl: str = "en", gl: str = "in", **kwargs):
        super().__init__(**kwargs)
        self._hl = hl
        self._gl = gl

    def _fetch_impl(self, query: str, **kwargs) -> List[Candidate]:
        distance = kwargs.get("distance", 1)
        resp = requests.get(
            ENDPOINT,
            params={
                "client": "youtube", "q": query,
                "hl": self._hl, "gl": self._gl, "ds": "yt"
            },
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
        # YouTube returns JSONP sometimes; the firefox client returns clean JSON
        data = resp.json()
        suggestions = data[1] if len(data) > 1 else []
        return [
            Candidate(
                text=s if isinstance(s, str) else s[0],
                source=self.name, distance=distance,
                rank=i + 1, raw_query=query
            )
            for i, s in enumerate(suggestions)
            if s
        ]
