"""
Ollama LLM adapter — optional, requires Ollama running locally.

Uses a local LLM to brainstorm related services, problems, audiences,
and alternative phrasings for the seed topic.
"""

from __future__ import annotations

from typing import List

import requests

from keyword_analysis.adapters.base import BaseAdapter, Candidate
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)

PROMPT_TEMPLATE = """You are an SEO keyword researcher. Given the topic "{seed}", brainstorm a list of related search terms that real customers would type into Google. Focus on:
- Related services and sub-services
- Common problems customers face
- Questions customers ask
- Different audience segments
- Alternative phrasings and local terminology
- Long-tail, specific phrases (3-6 words)

Return ONLY a numbered list of search terms, one per line. No explanations. Generate exactly {n} terms."""


class OllamaAdapter(BaseAdapter):
    name = "ollama"

    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434",
                 timeout: int = 30, max_suggestions: int = 20, **kwargs):
        super().__init__(**kwargs)
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_suggestions = max_suggestions

    def _fetch_impl(self, query: str, **kwargs) -> List[Candidate]:
        prompt = PROMPT_TEMPLATE.format(seed=query, n=self._max_suggestions)

        resp = requests.post(
            f"{self._base_url}/api/generate",
            json={"model": self._model, "prompt": prompt, "stream": False},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "")

        # Parse numbered list
        candidates = []
        for line in text.strip().split("\n"):
            line = line.strip()
            # Remove numbering (1. 2. etc.)
            import re
            line = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
            # Remove quotes
            line = line.strip('"').strip("'").strip()
            if line and len(line.split()) >= 2:
                candidates.append(
                    Candidate(text=line, source=self.name, distance=1, raw_query=query)
                )

        return candidates[:self._max_suggestions]

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self._base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False
