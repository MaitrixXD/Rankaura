"""
Configuration loader.

Reads config.yaml (or a user-supplied path), validates it, and exposes
typed dataclass instances so the rest of the codebase doesn't touch raw dicts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import yaml


# ── Dataclasses ──────────────────────────────────────────────

@dataclass
class LocaleConfig:
    hl: str = "en"
    gl: str = "in"


@dataclass
class ThresholdConfig:
    keep_threshold: float = 0.45
    seed_threshold: float = 0.60


@dataclass
class ExpansionConfig:
    max_related_per_source: int = 20
    top_n_full_sweep: int = 2
    max_distance: int = 2
    frontier_cap: int = 15


@dataclass
class BudgetConfig:
    global_max_requests: int = 500
    delay_seconds: float = 0.4
    max_retries: int = 3
    retry_backoff: float = 1.5
    cache_ttl_hours: int = 72


@dataclass
class ProviderConfig:
    google_autocomplete: bool = True
    bing_autocomplete: bool = False
    youtube_autocomplete: bool = False
    amazon_autocomplete: bool = False
    datamuse: bool = True
    wordnet: bool = True
    wikipedia: bool = True
    stackexchange: bool = True
    reddit: bool = False
    ollama: bool = False


@dataclass
class SerpConfig:
    enabled: bool = False
    api_key: str = ""
    cx: str = ""
    daily_quota: int = 100
    safety_margin: int = 10
    max_keywords: int = 50


@dataclass
class OllamaConfig:
    model: str = "llama3"
    base_url: str = "http://localhost:11434"
    timeout: int = 30
    max_suggestions: int = 20


@dataclass
class ScoringWeights:
    demand: float = 0.30
    competition: float = 0.25
    specificity: float = 0.20
    intent: float = 0.15
    distance: float = 0.10


@dataclass
class ScoreBands:
    high: float = 0.65
    medium: float = 0.40


@dataclass
class ScoringConfig:
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    competition_fallback: float = 0.5
    score_bands: ScoreBands = field(default_factory=ScoreBands)


@dataclass
class ClusteringConfig:
    method: str = "kmeans"
    max_clusters: int = 15
    min_cluster_size: int = 3


@dataclass
class SimilarityConfig:
    method: str = "tfidf"
    embedding_model: str = "all-MiniLM-L6-v2"


@dataclass
class ModifierConfig:
    question_words: List[str] = field(default_factory=lambda: [
        "how", "why", "what", "which", "can", "does", "is", "where", "when", "who"
    ])
    intent_words: List[str] = field(default_factory=lambda: [
        "best", "top", "cost", "price", "near me", "for", "vs", "versus",
        "without", "with", "services", "cheap", "affordable", "hire", "find",
        "review", "alternative"
    ])
    letters: str = "abcdefghijklmnopqrstuvwxyz"


@dataclass
class FilterConfig:
    min_word_count: int = 2
    max_word_count: int = 10
    near_duplicate_threshold: float = 0.85
    brand_blocklist: List[str] = field(default_factory=list)


@dataclass
class Config:
    """Top-level configuration container."""
    locale: LocaleConfig = field(default_factory=LocaleConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    expansion: ExpansionConfig = field(default_factory=ExpansionConfig)
    budget: BudgetConfig = field(default_factory=BudgetConfig)
    providers: ProviderConfig = field(default_factory=ProviderConfig)
    serp: SerpConfig = field(default_factory=SerpConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    clustering: ClusteringConfig = field(default_factory=ClusteringConfig)
    similarity: SimilarityConfig = field(default_factory=SimilarityConfig)
    modifiers: ModifierConfig = field(default_factory=ModifierConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)


# ── Loader ───────────────────────────────────────────────────

def _merge_dict_into_dataclass(dc, d: dict):
    """Recursively update a dataclass instance from a plain dict."""
    if d is None:
        return dc
    for key, value in d.items():
        if not hasattr(dc, key):
            continue
        current = getattr(dc, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _merge_dict_into_dataclass(current, value)
        else:
            setattr(dc, key, value)
    return dc


def load_config(path: Optional[str] = None) -> Config:
    """
    Load configuration from YAML.

    Resolution order:
    1. Explicit path argument
    2. KEYWORD_ANALYSIS_CONFIG env var
    3. ./config.yaml in the current working directory
    4. Pure defaults (no file needed)
    """
    if path is None:
        path = os.environ.get("KEYWORD_ANALYSIS_CONFIG")

    if path is None:
        # Look relative to this package's parent (project root)
        project_root = Path(__file__).resolve().parent.parent
        candidate = project_root / "config.yaml"
        if candidate.exists():
            path = str(candidate)

    cfg = Config()

    if path and Path(path).exists():
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        _merge_dict_into_dataclass(cfg, raw)

    return cfg
