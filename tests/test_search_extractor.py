import datetime as dt
import unittest

from tools.search.extractor import EvidenceExtractor
from tools.search.models import FetchedPage, SearchPlan, SearchResult
from tools.search.ranker import EvidenceRanker


class EvidenceExtractorTests(unittest.TestCase):
    def _page(self, text):
        result = SearchResult("Barcelona Results", "https://example.com/results", "", "searxng", 1, "barcelona")
        return FetchedPage("https://example.com/results", "Barcelona Results", text, result)

    def test_extracts_home_and_away_barcelona_scores(self):
        plan = SearchPlan(
            original_query="Barcelona last 5 La Liga results",
            question_type="sports_recent_results",
            queries=["query"],
            freshness_sensitive=True,
            target_team="Barcelona",
            competition="La Liga",
            requested_count=5,
        )
        page = self._page(
            "2026-05-10 | Barcelona | 2-0 | Real Madrid\n"
            "2026-05-03 | Girona | 1-3 | Barcelona\n"
        )

        matches, claims = EvidenceExtractor(today=dt.date(2026, 5, 12)).extract(plan, [page])

        self.assertEqual(len(matches), 2)
        self.assertEqual(matches[0].goals_for("Barcelona"), 2)
        self.assertEqual(matches[1].goals_for("Barcelona"), 3)
        self.assertEqual(claims, [])

    def test_filters_out_matches_without_target_team(self):
        plan = SearchPlan(
            original_query="Barcelona last 5 La Liga results",
            question_type="sports_recent_results",
            queries=["query"],
            freshness_sensitive=True,
            target_team="Barcelona",
            competition="La Liga",
            requested_count=5,
        )
        page = self._page("2026-05-10 | Atletico Madrid | 1-0 | Sevilla")

        matches, _ = EvidenceExtractor(today=dt.date(2026, 5, 12)).extract(plan, [page])

        self.assertEqual(matches, [])

    def test_extracts_generic_claims_for_research_query(self):
        plan = SearchPlan("explain attention", "research", ["query"])
        page = self._page("Attention lets a model weight tokens by relevance. Short.")

        matches, claims = EvidenceExtractor(today=dt.date(2026, 5, 12)).extract(plan, [page])

        self.assertEqual(matches, [])
        self.assertEqual(claims[0].claim, "Attention lets a model weight tokens by relevance.")

    def test_ranker_scores_direct_recent_match_evidence(self):
        plan = SearchPlan(
            original_query="Barcelona last 5 La Liga results",
            question_type="sports_recent_results",
            queries=["query"],
            freshness_sensitive=True,
            target_team="Barcelona",
            competition="La Liga",
            requested_count=5,
        )
        page = self._page("2026-05-10 | Barcelona | 2-0 | Real Madrid")
        matches, claims = EvidenceExtractor(today=dt.date(2026, 5, 12)).extract(plan, [page])

        ranked_matches, ranked_claims = EvidenceRanker().rank(plan, matches, claims)

        self.assertGreater(ranked_matches[0].score, 1.0)
        self.assertEqual(ranked_claims, [])

    def test_extracts_multiple_claims_and_filters_nav(self):
        plan = SearchPlan("explain attention", "research", ["query"])
        page = self._page(
            "Main page Contents Current events. "
            "Attention lets a model weight tokens by relevance. "
            "Self-attention allows the model to look at other tokens. "
            "Terms of use create account log in."
        )

        matches, claims = EvidenceExtractor(today=dt.date(2026, 5, 12)).extract(plan, [page])

        self.assertEqual(len(claims), 2)
        self.assertEqual(claims[0].claim, "Attention lets a model weight tokens by relevance.")
        self.assertEqual(claims[1].claim, "Self-attention allows the model to look at other tokens.")


if __name__ == "__main__":
    unittest.main()
