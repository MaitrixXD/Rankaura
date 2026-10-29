"""
Automated tests for the Keyword Analysis Engine.
"""

import unittest
from keyword_analysis.config import Config, load_config
from keyword_analysis.similarity.lightweight import LightweightSimilarity
from keyword_analysis.stages.enrich import EnrichStage, EnrichedKeyword
from keyword_analysis.stages.filter import FilterStage
from keyword_analysis.stages.score import ScoreStage
from keyword_analysis.utils.normalizer import deduplicate, extract_ngrams, jaccard_similarity, normalize


class TestNormalizer(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize("  Interior  Designer! "), "interior designer")
        self.assertEqual(normalize("How-To Decorate?"), "how-to decorate")

    def test_jaccard_similarity(self):
        s1 = "interior designer for home"
        s2 = "interior designer for homes"
        sim = jaccard_similarity(s1, s2)
        self.assertGreater(sim, 0.5)

    def test_extract_ngrams(self):
        text = "how much does an interior designer cost"
        ng = extract_ngrams(text, min_n=2, max_n=3)
        self.assertIn("interior designer", ng)
        self.assertIn("designer cost", ng)


class TestLightweightSimilarity(unittest.TestCase):
    def setUp(self):
        self.sim = LightweightSimilarity()

    def test_relevance_drift(self):
        seed = "interior designer"
        relevant = "interior design ideas"
        off_topic = "car tire alignment"

        score_rel = self.sim.compute_similarity(relevant, seed)
        score_off = self.sim.compute_similarity(off_topic, seed)

        self.assertGreater(score_rel, score_off)
        self.assertGreater(score_rel, 0.40)
        self.assertLess(score_off, 0.20)


class TestFilterAndScoring(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.filter_stage = FilterStage(self.cfg)
        self.score_stage = ScoreStage(self.cfg)

    def test_score_bounded(self):
        kw = EnrichedKeyword(
            text="affordable interior designer near me",
            unique_sources=3,
            source_names=["google", "datamuse", "stackexchange"],
            best_autocomplete_rank=1,
            word_count=5,
            similarity_to_seed=0.85,
            distance=1,
            intent_class="transactional",
            modifier_flags={"has_price": True, "has_location": True},
        )

        results = self.score_stage.run([kw])
        self.assertEqual(len(results), 1)
        scored = results[0]

        # Must be bounded strictly between 0 and 1
        self.assertGreaterEqual(scored.opportunity_score, 0.0)
        self.assertLessEqual(scored.opportunity_score, 1.0)
        self.assertIn(scored.score_band, ["High", "Medium", "Low"])
        self.assertIn(scored.confidence, ["High", "Medium", "Low"])


if __name__ == "__main__":
    unittest.main()
