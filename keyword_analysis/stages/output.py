"""
Stage 6: Output

Formats and exports keyword analysis clusters into CSV and JSON.
Generates structured page/article recommendations.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from keyword_analysis.stages.cluster import KeywordCluster
from keyword_analysis.stages.score import ScoredKeyword
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)


class OutputStage:
    def __init__(self):
        pass

    @staticmethod
    def _format_recommendation(
        slot: int, role: str, placement: str, kw: ScoredKeyword, purpose: str
    ) -> Dict[str, Any]:
        comps = kw.components or {}
        demand_val = comps.get("demand", 0.5)
        comp_val = comps.get("competition", 0.5)

        # Search activity label
        if demand_val >= 0.70:
            activity = "Very High"
        elif demand_val >= 0.45:
            activity = "High"
        else:
            activity = "Moderate"

        # Ranking difficulty badge
        if kw.word_count <= 2 or comp_val >= 0.65:
            diff_label = "High Competition"
            diff_class = "diff-hard"
        elif kw.word_count == 3 or comp_val >= 0.45:
            diff_label = "Medium Competition"
            diff_class = "diff-moderate"
        else:
            diff_label = "Low Competition"
            diff_class = "diff-easy"

        return {
            "slot": slot,
            "role": role,
            "placement": placement,
            "keyword": kw.text,
            "purpose": purpose,
            "activity": activity,
            "difficulty": diff_label,
            "diff_class": diff_class,
        }

    @staticmethod
    def recommend_top5(
        scored: List[ScoredKeyword], seed: str
    ) -> List[Dict[str, Any]]:
        """
        Algorithmic selection of the 5 Best Target Keywords for On-Page SEO Ranking.
        Slots:
        1. Core Page Anchor (<title> & <h1>)
        2. High-Intent Practical Qualifier (Primary <h2> & Core Section)
        3. Featured Snippet / Question Target (FAQ / Problem Section)
        4. Comparative Depth Anchor (Evaluation / Why Choose Us)
        5. Semantic Entity Expansion (Body Text & Supporting Themes)
        """
        if not scored:
            return []

        norm_seed = seed.strip().lower()

        # Step 1: Filter to the "Rankable Sweet Spot"
        # - Word Length: 3 to 6 words (strips saturated 1–2 word head terms and spammy 8+ word phrases)
        # - Search Consensus: Must appear in at least 2 independent discovery sources
        # - Similarity Gate: Semantic similarity to seed between 0.60 and 0.85
        sweet_spot = [
            k for k in scored
            if k.text.lower() != norm_seed
            and 3 <= k.word_count <= 6
            and k.unique_sources >= 2
            and 0.60 <= k.similarity_to_seed <= 0.85
        ]
        # Tiered fallbacks if sweet spot is too narrow for small candidate pools
        if len(sweet_spot) < 5:
            sweet_spot = [
                k for k in scored
                if k.text.lower() != norm_seed
                and 3 <= k.word_count <= 6
                and 0.50 <= k.similarity_to_seed <= 0.90
            ]
        if len(sweet_spot) < 5:
            sweet_spot = [
                k for k in scored
                if k.text.lower() != norm_seed and 3 <= k.word_count <= 6
            ]
        if len(sweet_spot) < 5:
            sweet_spot = [k for k in scored if k.text.lower() != norm_seed]
        if not sweet_spot:
            sweet_spot = list(scored)

        candidates = sweet_spot

        def get_demand(k: ScoredKeyword) -> float:
            return k.components.get("demand", 0.5) if k.components else 0.5

        def get_opp(k: ScoredKeyword) -> float:
            return k.opportunity_score

        selected_texts: Set[str] = set()
        chosen: List[Dict[str, Any]] = []

        # Slot 1: Core Page Anchor (Title & H1)
        # Prefers 3-5 words, closest semantic anchor with strong demand
        slot1_cands = [k for k in candidates if 3 <= k.word_count <= 5] or candidates
        slot1_cands.sort(
            key=lambda k: (get_demand(k) * 0.6 + k.similarity_to_seed * 0.4),
            reverse=True,
        )
        slot1_kw = slot1_cands[0]
        selected_texts.add(slot1_kw.text)
        chosen.append(
            OutputStage._format_recommendation(
                slot=1,
                role="Page Title & Main Heading",
                placement="Page Title & Main Heading",
                kw=slot1_kw,
                purpose="Use in your page title and main heading to match core search intent.",
            )
        )

        # Slot 2: High-Intent Practical Qualifier (Primary H2 & Core Section)
        practical_pat = re.compile(
            r"\b(service|services|pricing|cost|packages|process|agency|checklist|company|for small business|for beginners|workflow|portfolio|firm|tools|hire|online)\b",
            re.IGNORECASE,
        )
        slot2_cands = [
            k
            for k in candidates
            if k.text not in selected_texts and practical_pat.search(k.text)
        ]
        if not slot2_cands:
            slot2_cands = [k for k in candidates if k.text not in selected_texts]
        if slot2_cands:
            slot2_cands.sort(
                key=lambda k: (get_demand(k) * 0.5 + get_opp(k) * 0.5),
                reverse=True,
            )
            slot2_kw = slot2_cands[0]
            selected_texts.add(slot2_kw.text)
            chosen.append(
                OutputStage._format_recommendation(
                    slot=2,
                    role="Main Content Section",
                    placement="Main Content Section",
                    kw=slot2_kw,
                    purpose="Use in your main content to highlight value, solutions, and pricing.",
                )
            )

        # Slot 3: Featured Snippet / Question Target (FAQ or Problem-Solution H2)
        question_pat = re.compile(
            r"\b(how|what|why|guide|tips|ideas|tutorial|difference between|checklist|steps|can you|should you|cost of|meaning)\b",
            re.IGNORECASE,
        )
        slot3_cands = [
            k
            for k in candidates
            if k.text not in selected_texts and question_pat.search(k.text)
        ]
        if not slot3_cands:
            slot3_cands = [
                k
                for k in candidates
                if k.text not in selected_texts
                and re.search(r"\b(for|with|in|to)\b", k.text)
            ]
        if not slot3_cands:
            slot3_cands = [k for k in candidates if k.text not in selected_texts]
        if slot3_cands:
            def auto_rank_score(k: ScoredKeyword) -> float:
                rank = k.best_autocomplete_rank or 10
                return (11 - rank) + get_demand(k) * 5

            slot3_cands.sort(key=auto_rank_score, reverse=True)
            slot3_kw = slot3_cands[0]
            selected_texts.add(slot3_kw.text)
            chosen.append(
                OutputStage._format_recommendation(
                    slot=3,
                    role="FAQ Content",
                    placement="FAQ Content",
                    kw=slot3_kw,
                    purpose="Use in your FAQ section to answer common user questions.",
                )
            )

        # Slot 4: Comparative Depth Anchor (Evaluation / Why Choose Us)
        comp_pat = re.compile(
            r"\b(best|top|vs|versus|review|reviews|comparison|compare|alternatives|alternative|checklist|examples|features|benefits)\b",
            re.IGNORECASE,
        )
        slot4_cands = [
            k
            for k in candidates
            if k.text not in selected_texts and comp_pat.search(k.text)
        ]
        if not slot4_cands:
            slot4_cands = [
                k
                for k in candidates
                if k.text not in selected_texts and k.word_count >= 4
            ]
        if not slot4_cands:
            slot4_cands = [k for k in candidates if k.text not in selected_texts]
        if slot4_cands:
            slot4_cands.sort(
                key=lambda k: (get_opp(k) * 0.6 + get_demand(k) * 0.4),
                reverse=True,
            )
            slot4_kw = slot4_cands[0]
            selected_texts.add(slot4_kw.text)
            chosen.append(
                OutputStage._format_recommendation(
                    slot=4,
                    role="Comparison Section",
                    placement="Comparison Section",
                    kw=slot4_kw,
                    purpose="Use in a comparison section to highlight key differences.",
                )
            )

        # Slot 5: Semantic Entity Expansion (Body Paragraphs & Alt Text)
        selected_words: Set[str] = set()
        for t in selected_texts:
            selected_words.update(t.split())

        slot5_cands = [k for k in candidates if k.text not in selected_texts]
        if slot5_cands:
            def entity_divergence_score(k: ScoredKeyword) -> float:
                cand_words = set(k.text.split())
                overlap = len(cand_words & selected_words)
                return (get_demand(k) * 0.7) - (overlap * 0.3) + (k.similarity_to_seed * 0.4)

            slot5_cands.sort(key=entity_divergence_score, reverse=True)
            slot5_kw = slot5_cands[0]
            selected_texts.add(slot5_kw.text)
            chosen.append(
                OutputStage._format_recommendation(
                    slot=5,
                    role="Supporting Content",
                    placement="Supporting Content",
                    kw=slot5_kw,
                    purpose="Use in supporting content to cover related topics and variations.",
                )
            )

        return chosen

    @staticmethod
    def to_dict(
        clusters: List[KeywordCluster],
        seed: str,
        scored: Optional[List[ScoredKeyword]] = None,
    ) -> Dict[str, Any]:
        """Convert analysis clusters to JSON-serializable dictionary with 5 best recommendations."""
        out_clusters = []
        for c in clusters:
            out_clusters.append({
                "cluster_id": c.cluster_id,
                "cluster_topic": c.name,
                "intent": c.intent_class,
                "average_opportunity": c.average_opportunity,
                "primary_keyword": {
                    "keyword": c.primary_keyword.text,
                    "opportunity_score": c.primary_keyword.opportunity_score,
                    "score_band": c.primary_keyword.score_band,
                    "confidence": c.primary_keyword.confidence,
                    "components": c.primary_keyword.components,
                    "unique_sources": c.primary_keyword.unique_sources,
                    "best_rank": c.primary_keyword.best_autocomplete_rank,
                    "word_count": c.primary_keyword.word_count,
                },
                "supporting_keywords": [
                    {
                        "keyword": s.text,
                        "opportunity_score": s.opportunity_score,
                        "score_band": s.score_band,
                        "confidence": s.confidence,
                        "components": s.components,
                        "unique_sources": s.unique_sources,
                        "best_rank": s.best_autocomplete_rank,
                        "word_count": s.word_count,
                    }
                    for s in c.supporting_keywords
                ],
            })

        # Gather all scored keywords for recommendation
        all_scored: List[ScoredKeyword] = []
        if scored is not None:
            all_scored = scored
        else:
            for c in clusters:
                all_scored.append(c.primary_keyword)
                all_scored.extend(c.supporting_keywords)

        recommended_5 = OutputStage.recommend_top5(all_scored, seed)

        return {
            "seed_topic": seed,
            "total_clusters": len(clusters),
            "total_keywords": sum(c.total_keywords for c in clusters),
            "recommended_5": recommended_5,
            "clusters": out_clusters,
        }

    @staticmethod
    def to_csv(clusters: List[KeywordCluster], seed: str) -> str:
        """Export all clustered keywords into a flat CSV format."""
        output = StringIO()
        writer = csv.writer(output)

        # Header row
        writer.writerow([
            "Cluster ID",
            "Cluster Topic",
            "Role",
            "Keyword",
            "Opportunity Score",
            "Score Band",
            "Confidence",
            "Intent",
            "Demand Proxy",
            "Competition Estimate",
            "Specificity Score",
            "Intent Score",
            "Distance Penalty",
            "Unique Sources Count",
            "Best Autocomplete Rank",
            "Word Count",
        ])

        for c in clusters:
            # Primary keyword row
            p = c.primary_keyword
            writer.writerow([
                c.cluster_id,
                c.name,
                "PRIMARY",
                p.text,
                p.opportunity_score,
                p.score_band,
                p.confidence,
                p.intent_class,
                p.components.get("demand", ""),
                p.components.get("competition", ""),
                p.components.get("specificity", ""),
                p.components.get("intent", ""),
                p.components.get("distance_penalty", ""),
                p.unique_sources,
                p.best_autocomplete_rank or "N/A",
                p.word_count,
            ])

            # Supporting keywords
            for s in c.supporting_keywords:
                writer.writerow([
                    c.cluster_id,
                    c.name,
                    "SUPPORTING",
                    s.text,
                    s.opportunity_score,
                    s.score_band,
                    s.confidence,
                    s.intent_class,
                    s.components.get("demand", ""),
                    s.components.get("competition", ""),
                    s.components.get("specificity", ""),
                    s.components.get("intent", ""),
                    s.components.get("distance_penalty", ""),
                    s.unique_sources,
                    s.best_autocomplete_rank or "N/A",
                    s.word_count,
                ])

        return output.getvalue()

    def export_files(
        self, clusters: List[KeywordCluster], seed: str, base_filepath: str
    ) -> Dict[str, str]:
        """Save both CSV and JSON to disk."""
        p = Path(base_filepath)
        p.parent.mkdir(parents=True, exist_ok=True)

        json_path = p.with_suffix(".json")
        csv_path = p.with_suffix(".csv")

        json_data = self.to_dict(clusters, seed)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)

        csv_data = self.to_csv(clusters, seed)
        with open(csv_path, "w", encoding="utf-8") as f:
            f.write(csv_data)

        log.info("Results exported to %s and %s", json_path, csv_path)
        return {"json": str(json_path), "csv": str(csv_path)}
