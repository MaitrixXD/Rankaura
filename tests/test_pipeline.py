"""
Automated tests for the Keyword Analysis Engine.
"""

import unittest
from keyword_analysis.config import Config, load_config
from keyword_analysis.similarity.lightweight import LightweightSimilarity
from keyword_analysis.stages.enrich import EnrichStage, EnrichedKeyword
from keyword_analysis.stages.filter import FilterStage
from keyword_analysis.stages.score import ScoreStage, ScoredKeyword
from keyword_analysis.stages.verify import VerifyStage
from keyword_analysis.adapters.llm import GeminiAdapter
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


class TestVerifyStage(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()
        self.cfg.providers.gemini = True
        # Mock Gemini adapter
        class MockGemini(GeminiAdapter):
            def __init__(self):
                pass
            def is_available(self):
                return True
            def verify_keywords(self, seed, keywords):
                return keywords[:5]

        self.mock_gemini = MockGemini()
        self.verify_stage = VerifyStage(self.cfg, gemini_adapter=self.mock_gemini)

    def test_verify_run(self):
        kw1 = ScoredKeyword(text="kw1", opportunity_score=0.9, score_band="High", confidence="High", components={}, intent_class="t", unique_sources=2, source_names=[], best_autocomplete_rank=1, word_count=2, distance=1, similarity_to_seed=0.9)
        kw2 = ScoredKeyword(text="kw2", opportunity_score=0.8, score_band="High", confidence="High", components={}, intent_class="t", unique_sources=2, source_names=[], best_autocomplete_rank=1, word_count=2, distance=1, similarity_to_seed=0.8)
        
        results = self.verify_stage.run("seed", [kw1, kw2])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].text, "kw1")


if __name__ == "__main__":
    unittest.main()
