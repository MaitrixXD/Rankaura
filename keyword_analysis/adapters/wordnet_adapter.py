"""
WordNet adapter via NLTK — offline, no network calls.

Extracts synonyms, hypernyms, and hyponyms for the seed.
Known issue: WordNet returns wrong word senses (e.g. "interior" → automotive).
The similarity gate in the Expand stage handles this; this adapter does not filter.
"""

from __future__ import annotations

from typing import List, Set

from keyword_analysis.adapters.base import BaseAdapter, Candidate
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)

_NLTK_READY = False


def _ensure_nltk():
    """Download WordNet data if needed (one-time)."""
    global _NLTK_READY
    if _NLTK_READY:
        return
    import nltk
    for resource in ["wordnet", "omw-1.4"]:
        try:
            nltk.data.find(f"corpora/{resource}")
        except LookupError:
            nltk.download(resource, quiet=True)
    _NLTK_READY = True


class WordNetAdapter(BaseAdapter):
    name = "wordnet"

    def __init__(self, max_results: int = 20, **kwargs):
        super().__init__(**kwargs)
        self._max_results = max_results

    def _fetch_impl(self, query: str, **kwargs) -> List[Candidate]:
        _ensure_nltk()
        from nltk.corpus import wordnet as wn

        words: Set[str] = set()
        # Query may be multi-word; try each word and the full phrase
        query_parts = query.lower().split()
        search_terms = query_parts + ["_".join(query_parts)] if len(query_parts) > 1 else query_parts

        for term in search_terms:
            for synset in wn.synsets(term):
                # Synonyms (lemma names)
                for lemma in synset.lemmas():
                    name = lemma.name().replace("_", " ")
                    if name.lower() != query.lower():
                        words.add(name)

                # Hypernyms (broader concepts)
                for hyper in synset.hypernyms():
                    for lemma in hyper.lemmas():
                        name = lemma.name().replace("_", " ")
                        words.add(name)

                # Hyponyms (more specific concepts)
                for hypo in synset.hyponyms():
                    for lemma in hypo.lemmas():
                        name = lemma.name().replace("_", " ")
                        words.add(name)

            if len(words) >= self._max_results * 2:
                break

        results = sorted(words)[:self._max_results]
        return [
            Candidate(text=w, source=self.name, distance=1, raw_query=query)
            for w in results
        ]

    def is_available(self) -> bool:
        try:
            _ensure_nltk()
            return True
        except Exception:
            return False
