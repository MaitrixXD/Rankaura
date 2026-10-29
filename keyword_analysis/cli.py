"""
Command-line interface (CLI) for the Keyword Analysis Engine.

Usage:
  python -m keyword_analysis.cli "interior designer" --output results/interior_designer
"""

from __future__ import annotations

import argparse
import sys
from keyword_analysis.config import load_config
from keyword_analysis.pipeline import KeywordPipeline


def main():
    parser = argparse.ArgumentParser(
        description="Free SEO Keyword Discovery & Clustering Engine"
    )
    parser.add_argument("seed", type=str, help="Seed topic or service (e.g. 'interior designer')")
    parser.add_argument("--hl", type=str, default="en", help="Language code (default: en)")
    parser.add_argument("--gl", type=str, default="in", help="Country code (default: in)")
    parser.add_argument("--keep-threshold", type=float, default=None, help="Drift keep threshold (default: 0.45)")
    parser.add_argument("--seed-threshold", type=float, default=None, help="Expansion seed threshold (default: 0.60)")
    parser.add_argument("--output", type=str, default=None, help="Base path to export CSV/JSON (e.g. 'results/seed')")

    args = parser.parse_args()

    cfg = load_config()
    cfg.locale.hl = args.hl
    cfg.locale.gl = args.gl
    if args.keep_threshold is not None:
        cfg.thresholds.keep_threshold = args.keep_threshold
    if args.seed_threshold is not None:
        cfg.thresholds.seed_threshold = args.seed_threshold

    print(f"\n[+] Running Keyword Analysis Engine for: '{args.seed}' (Locale: {args.hl}/{args.gl})")
    pipeline = KeywordPipeline(cfg)
    result = pipeline.run(args.seed, export_base_path=args.output)

    print("\n" + "=" * 70)
    print(f"RESULTS FOR '{result.seed}' in {result.execution_time_seconds}s")
    print(f"Discovered: {result.total_raw_candidates} raw -> {result.kept_count} kept -> {result.clusters_count} clusters")
    print("=" * 70)

    # Collect and sort all individual keywords across clusters
    all_kws = []
    seen = set()
    for c in result.clusters:
        if c.primary_keyword and c.primary_keyword.text not in seen:
            all_kws.append(c.primary_keyword)
            seen.add(c.primary_keyword.text)
        for s in c.supporting_keywords:
            if s.text not in seen:
                all_kws.append(s)
                seen.add(s.text)
    all_kws.sort(key=lambda k: k.opportunity_score, reverse=True)

    print("\n⭐ TOP 5 HIGHEST-OPPORTUNITY KEYWORDS (ACROSS ALL CLUSTERS):")
    print("-" * 70)
    print(f"{'Rank':<6} | {'Keyword':<35} | {'Score':<8} | {'Band':<8} | {'Intent'}")
    print("-" * 70)
    for idx, kw in enumerate(all_kws[:5]):
        print(f"#{idx+1:<5} | {kw.text:<35} | {kw.opportunity_score:<8} | {kw.score_band:<8} | {kw.intent_class}")
    print("-" * 70)

    print("\nCONTENT CLUSTERS (PAGE RECOMMENDATIONS):")
    for c in result.clusters[:6]:
        p = c.primary_keyword
        print(f"\nCluster #{c.cluster_id} [{c.intent_class.upper()}]: '{c.name}' (Avg Opp: {c.average_opportunity})")
        print(f"  Primary:    {p.text} [Score: {p.opportunity_score} | Band: {p.score_band} | Conf: {p.confidence}]")
        print(f"              Demand: {p.components.get('demand')} | Comp: {p.components.get('competition')} | Spec: {p.components.get('specificity')}")
        if c.supporting_keywords:
            sups = ", ".join(f"'{s.text}' ({s.opportunity_score})" for s in c.supporting_keywords[:4])
            print(f"  Supporting: {sups}")

    if args.output:
        print(f"\n[✓] Results exported to {args.output}.csv and {args.output}.json")


if __name__ == "__main__":
    main()
