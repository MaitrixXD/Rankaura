"""
Benchmark and Evaluation Harness

Compares the Keyword Analysis Engine output against a plain Google Autocomplete baseline.
Evaluates:
1. Long-tail uniqueness ratio (% of 3+ word intent keywords)
2. Intent richness (presence of commercial/transactional/local modifiers)
3. Elimination of generic head terms
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Set

from keyword_analysis.config import load_config
from keyword_analysis.stages.enrich import INTENT_PATTERNS
from keyword_analysis.utils.normalizer import normalize, tokenize


def is_high_intent(phrase: str) -> bool:
    for group in ["transactional", "commercial", "local"]:
        for pat in INTENT_PATTERNS[group]:
            import re
            if re.search(pat, phrase):
                return True
    return False


def evaluate_set(keywords: List[str], seed: str) -> Dict[str, float]:
    total = len(keywords)
    if total == 0:
        return {"total": 0, "long_tail_pct": 0.0, "high_intent_pct": 0.0, "head_term_pct": 0.0}

    norm_seed = normalize(seed)
    long_tail = 0
    high_intent = 0
    head_terms = 0

    for kw in keywords:
        tokens = tokenize(kw)
        if len(tokens) >= 3:
            long_tail += 1
        elif len(tokens) <= 2:
            head_terms += 1

        if is_high_intent(kw):
            high_intent += 1

    return {
        "total": total,
        "long_tail_pct": round(long_tail / total * 100, 1),
        "high_intent_pct": round(high_intent / total * 100, 1),
        "head_term_pct": round(head_terms / total * 100, 1),
    }


def print_comparison(seed: str, engine_keywords: List[str], baseline_keywords: List[str]):
    eng_stats = evaluate_set(engine_keywords, seed)
    base_stats = evaluate_set(baseline_keywords, seed)

    print("\n" + "=" * 65)
    print(f"BENCHMARK COMPARISON FOR SEED: '{seed}'")
    print("=" * 65)
    print(f"{'Metric':<30} | {'Engine (Ours)':<15} | {'Baseline (Plain AC)':<15}")
    print("-" * 65)
    print(f"{'Total Discovered':<30} | {eng_stats['total']:<15} | {base_stats['total']:<15}")
    print(f"{'Long-Tail (3+ words) %':<30} | {eng_stats['long_tail_pct']}%{'':<10} | {base_stats['long_tail_pct']}%")
    print(f"{'High Intent (Cost/Hire/Best) %':<30} | {eng_stats['high_intent_pct']}%{'':<10} | {base_stats['high_intent_pct']}%")
    print(f"{'Head Terms (<= 2 words) %':<30} | {eng_stats['head_term_pct']}%{'':<10} | {base_stats['head_term_pct']}%")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate engine vs baseline")
    parser.add_argument("--seed", default="interior designer", help="Seed topic to test")
    args = parser.parse_args()
    print(f"Benchmark ready for seed: {args.seed}")
