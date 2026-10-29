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

# Lazy import to avoid circular dependency at module level
_is_safe_top_keyword = None
def _get_safe_checker():
    global _is_safe_top_keyword
    if _is_safe_top_keyword is None:
        from keyword_analysis.stages.filter import is_safe_top_keyword
        _is_safe_top_keyword = is_safe_top_keyword
    return _is_safe_top_keyword

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


class GeminiAdapter(BaseAdapter):
    name = "gemini"

    def __init__(self, api_key: str = "", model: str = "gemini-2.5-flash", timeout: int = 25, **kwargs):
        super().__init__(**kwargs)
        import os
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._model = model
        self._timeout = timeout

    @property
    def url(self) -> str:
        return f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent?key={self._api_key}"

    def _fetch_impl(self, query: str, **kwargs) -> List[Candidate]:
        # For expansion, we use a similar prompt to Ollama
        prompt = PROMPT_TEMPLATE.format(seed=query, n=20)
        return self.generate_keywords(prompt, query)

    def generate_keywords(self, prompt: str, raw_query: str) -> List[Candidate]:
        if not self._api_key:
            log.warning("No Gemini API key provided. Skipping Gemini expansion.")
            return []

        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }

        try:
            resp = requests.post(self.url, json=payload, timeout=self._timeout)
            resp.raise_for_status()
            data = resp.json()

            text = data["candidates"][0]["content"]["parts"][0]["text"]

            candidates = []
            for line in text.strip().split("\n"):
                line = line.strip()
                import re
                line = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
                line = line.strip('"').strip("'").strip()
                if line and len(line.split()) >= 2:
                    candidates.append(
                        Candidate(text=line, source=self.name, distance=1, raw_query=raw_query)
                    )
            return candidates
        except Exception as e:
            log.error(f"Gemini API error: {e}")
            return []

    def verify_keywords(self, seed: str, keywords: List[str]) -> List[str]:
        """
        Verifies and ranks the best keywords using Gemini.
        Applies strict filtering rules against locations, irrelevant brands, songs, jobs, and nonsense.
        Returns up to 10 keywords (5 High Competition, 5 Medium Competition).
        """
        if not self._api_key:
            import os
            self._api_key = os.environ.get("GEMINI_API_KEY", "")
        if not self._api_key:
            log.warning("No Gemini API key available for verification; falling back to algorithmic filter.")
            safe_check = _get_safe_checker()
            return [kw for kw in keywords if safe_check(kw, seed)][:10]

        prompt = f"""You are a high-level SEO Strategist. Your goal is to identify the 10 most professional, high-impact target keywords for on-page SEO ranking for the topic "{seed}".

TARGET COMPANY CONTEXT: The company is based in Mumbai, Maharashtra, India.

STRICT FILTERING & EXCLUSION RULES (MANDATORY):
1. GEOGRAPHIC TARGETING: Immediately DISCARD any keyword containing an international city, state, or country (e.g. "usa", "uk", "vietnam", "dubai", "lahore", "karachi", "pakistan", "bangladesh", "nepal", "sri lanka").
2. LOCAL DOMESTIC RULES: Immediately DISCARD any Indian city/state that is NOT Mumbai, Maharashtra, or India. Strictly DISCARD "in noida", "bengaluru", "pune", "delhi", "gurgaon", "ahmedabad", "chennai", "hyderabad", etc. Only "Mumbai", "Maharashtra", and "India" are permitted.
3. NO IRRELEVANT BRANDS OR PEOPLE: Discard obscure company names, individual designers (e.g., "alberto pinto"), or brand names that hijack the generic topic.
4. NO SONGS / MUSIC / MOVIES: Discard entertainment queries unless the seed topic is explicitly about music.
5. NO JOBS / EMPLOYMENT: Discard job postings, vacancies, salaries, or recruitment queries.
6. NO NONSENSE / FRAGMENTS / JUNK: Discard single-letter artifacts (e.g., "c interior design", "g design"), nonsense phrases, and technical artifacts ("gcc").
7. NO ADMINISTRATIVE / LEGAL / COMPLIANCE JUNK: Strictly DISCARD keywords containing "hsn code", "sac code", "gst rate", "gst registration", "sac", "hsn", "tax", "code", or other administrative/legal terms. These are NOT SEO keywords for service discovery.
8. HIGH VALUE INTENT: Select only high-intent, professional keywords representing core solutions, services, FAQs, comparisons, or architectures.

If a keyword contains "hsn code" or any location other than Mumbai/Maharashtra/India, it MUST be removed. No exceptions.

Topic: "{seed}"
Candidate Keywords:
""" + "\n".join(f"- {kw}" for kw in keywords) + """

Please return exactly 10 keywords:
- The first 5 should be High Competition (core, high-volume head terms)
- The next 5 should be Medium Competition (more specific, long-tail phrases)

Return ONLY the 10 keywords, one per line. Do NOT include numbers, bullet points, asterisks, headers, or explanations."""

        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }

        models_to_try = [self._model]
        for fb in ["gemini-3.5-flash", "gemini-3.8-flash", "gemini-flash-latest"]:
            if fb not in models_to_try:
                models_to_try.append(fb)

        text = None
        for m in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={self._api_key}"
            try:
                resp = requests.post(url, json=payload, timeout=min(self._timeout, 15))
                resp.raise_for_status()
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                if text:
                    break
            except Exception as e:
                log.warning("Gemini model '%s' request failed (%s), trying fallback...", m, e)

        if text:
            verified = [line.strip("- *#").strip() for line in text.strip().split("\n") if line.strip()]
            safe_check = _get_safe_checker()
            verified = [kw for kw in verified if safe_check(kw, seed)]
            log.info("Gemini verified %d clean keywords for '%s'", len(verified), seed)
            if verified:
                return verified[:10]

        log.warning("Gemini verification had no valid keywords or all models failed; applying safe fallback.")
        safe_check = _get_safe_checker()
        safe_fallback = [kw for kw in keywords if safe_check(kw, seed)]
        return safe_fallback[:10]

    def is_available(self) -> bool:
        return bool(self._api_key)
