"""
Stage 5: Cluster

Groups scored keywords into semantic clusters split by intent.
One cluster = One target page or article.
Designates the highest-opportunity keyword as Primary, and the rest as Supporting keywords.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np

from keyword_analysis.config import Config
from keyword_analysis.stages.filter import has_junk_letter
from keyword_analysis.similarity.embeddings import EmbeddingSimilarity
from keyword_analysis.stages.score import ScoredKeyword
from keyword_analysis.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class KeywordCluster:
    cluster_id: int
    name: str
    intent_class: str
    primary_keyword: ScoredKeyword
    supporting_keywords: List[ScoredKeyword] = field(default_factory=list)
    average_opportunity: float = 0.0

    @property
    def total_keywords(self) -> int:
        return 1 + len(self.supporting_keywords)


class ClusterStage:
    def __init__(self, config: Config):
        self.cfg = config

    def _cluster_group(
        self, keywords: List[ScoredKeyword], intent: str, start_id: int
    ) -> List[KeywordCluster]:
        """Cluster a set of keywords sharing the same intent."""
        if not keywords:
            return []

        # If too few items, return single cluster
        if len(keywords) <= 3:
            # Pick first safe keyword as primary
            primary = keywords[0]
            supporting = keywords[1:]
            for i, kw in enumerate(keywords):
                if not has_junk_letter(kw.text):
                    primary = kw
                    supporting = keywords[:i] + keywords[i+1:]
                    break
            avg_opp = sum(k.opportunity_score for k in keywords) / len(keywords)
            return [
                KeywordCluster(
                    cluster_id=start_id,
                    name=primary.text,
                    intent_class=intent,
                    primary_keyword=primary,
                    supporting_keywords=supporting,
                    average_opportunity=round(avg_opp, 3),
                )
            ]

        # Vectorize using TF-IDF
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.cluster import KMeans

        texts = [k.text for k in keywords]
        vec = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        matrix = vec.fit_transform(texts)

        # Decide k: roughly 1 cluster per 4-7 keywords, capped by config
        k = max(2, min(len(keywords) // 4, self.cfg.clustering.max_clusters))
        k = min(k, len(keywords))

        kmeans = KMeans(n_clusters=k, random_state=42, n_init=5)
        labels = kmeans.fit_predict(matrix)

        clusters_by_label: Dict[int, List[ScoredKeyword]] = {i: [] for i in range(k)}
        for kw, lbl in zip(keywords, labels):
            clusters_by_label[lbl].append(kw)

        clusters: List[KeywordCluster] = []
        cur_id = start_id

        for lbl, group in clusters_by_label.items():
            if not group:
                continue
            # Sort group by opportunity score descending
            group.sort(key=lambda x: x.opportunity_score, reverse=True)
            # Pick first clean keyword as primary (skip junk artifacts)
            primary = group[0]
            supporting = group[1:]
            for i, kw in enumerate(group):
                if not has_junk_letter(kw.text):
                    primary = kw
                    supporting = group[:i] + group[i+1:]
                    break
            avg_opp = sum(x.opportunity_score for x in group) / len(group)

            clusters.append(
                KeywordCluster(
                    cluster_id=cur_id,
                    name=primary.text,
                    intent_class=intent,
                    primary_keyword=primary,
                    supporting_keywords=supporting,
                    average_opportunity=round(avg_opp, 3),
                )
            )
            cur_id += 1

        return clusters

    def run(self, keywords: List[ScoredKeyword]) -> List[KeywordCluster]:
        log.info("=== Starting Stage 5: Cluster (%d keywords) ===", len(keywords))
        if not keywords:
            return []

        # Cluster all keywords semantically by topical similarity
        all_clusters = self._cluster_group(keywords, intent="general", start_id=1)

        # Sort clusters by average opportunity descending
        all_clusters.sort(key=lambda c: c.average_opportunity, reverse=True)

        log.info("Stage 5 complete: %d keyword clusters created", len(all_clusters))
        return all_clusters
