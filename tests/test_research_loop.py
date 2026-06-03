from __future__ import annotations

import unittest
from unittest.mock import patch

from tools.research.loop import ResearchLoop
from tools.research.models import ResearchPlan, ResearchSubquery
from tools.search.models import EvidenceItem, EvidencePack, SearchPlan, SearchResult


class FakePlanner:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def plan(self, query: str, max_sources: int = 8) -> ResearchPlan:
        self.queries.append(query)
        return ResearchPlan(
            original_query=query,
            question_type="general_research",
            subqueries=[
                ResearchSubquery(
                    query="optional context",
                    purpose="Find optional background.",
                    required=False,
                ),
                ResearchSubquery(
                    query="required facts",
                    purpose="Find required facts.",
                    required=True,
                ),
            ],
            freshness_sensitive=False,
            preferred_source_types=["official source"],
            max_sources=max_sources,
        )


class FakeSearchPipeline:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def collect(self, query: str, num_results: int = 5) -> EvidencePack:
        self.queries.append(query)
        url = f"https://example.gov/{query.replace(' ', '-')}"
        result = SearchResult(
            title=query.title(),
            url=url,
            snippet=f"Snippet for {query}",
            provider="fake",
            rank=1,
            query=query,
        )
        return EvidencePack(
            plan=SearchPlan(
                original_query=query,
                question_type="general_research",
                queries=[query],
            ),
            results=[result],
            claims=[
                EvidenceItem(
                    claim=f"Claim for {query}",
                    url=url,
                    title=query.title(),
                    source="fake",
                )
            ],
            answer=f"Answer for {query}",
            confidence="high",
        )


class FreshPlanner:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def plan(self, query: str, max_sources: int = 8) -> ResearchPlan:
        self.queries.append(query)
        return ResearchPlan(
            original_query=query,
            question_type="general_research",
            subqueries=[
                ResearchSubquery(
                    query="optional context",
                    purpose="Find optional background.",
                    required=False,
                ),
                ResearchSubquery(
                    query="required facts",
                    purpose="Find required fresh facts.",
                    required=True,
                ),
            ],
            freshness_sensitive=True,
            preferred_source_types=["official source"],
            max_sources=max_sources,
        )


class SparseSearchPipeline(FakeSearchPipeline):
    def collect(self, query: str, num_results: int = 5) -> EvidencePack:
        self.queries.append(query)
        if query == "required facts":
            return EvidencePack(
                plan=SearchPlan(
                    original_query=query,
                    question_type="general_research",
                    queries=[query],
                ),
                results=[],
                claims=[],
                answer="",
                confidence="low",
            )
        return self._pack_with_evidence(query)

    def _pack_with_evidence(self, query: str) -> EvidencePack:
        url = f"https://example.gov/{query.replace(' ', '-')}"
        result = SearchResult(
            title=query.title(),
            url=url,
            snippet=f"Snippet for {query}",
            provider="fake",
            rank=1,
            query=query,
        )
        return EvidencePack(
            plan=SearchPlan(
                original_query=query,
                question_type="general_research",
                queries=[query],
            ),
            results=[result],
            claims=[
                EvidenceItem(
                    claim=f"Claim for {query}",
                    url=url,
                    title=query.title(),
                    source="fake",
                )
            ],
            answer=f"Answer for {query}",
            confidence="high",
        )


class ResearchLoopTests(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("core.llm.call_llm_once", side_effect=Exception("API offline"))
        self.mock_call = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_loop_creates_todos_and_returns_report(self) -> None:
        search_pipeline = FakeSearchPipeline()
        loop = ResearchLoop(
            search_pipeline=search_pipeline,
            planner=FakePlanner(),
            max_iterations=2,
        )

        report = loop.run("  test research  ", max_sources=8)

        self.assertEqual(search_pipeline.queries, ["required facts", "optional context"])
        self.assertIn("Short answer:", report)
        self.assertIn("Sources:", report)
        self.assertIn("Research progress:", report)
        self.assertIn("completed: 2", report)
        self.assertIn("Stop reason: complete", report)

    def test_empty_query_does_not_plan_or_search(self) -> None:
        planner = FakePlanner()
        search_pipeline = FakeSearchPipeline()
        loop = ResearchLoop(
            search_pipeline=search_pipeline,
            planner=planner,
            max_iterations=2,
        )

        report = loop.run("   ", max_sources=8)

        self.assertEqual(planner.queries, [])
        self.assertEqual(search_pipeline.queries, [])
        self.assertIn("No source evidence was available", report)
        self.assertIn("Confidence:\nlow", report)
        self.assertIn("Research progress:", report)
        self.assertIn("total: 0", report)
        self.assertIn("completed: 0", report)
        self.assertIn("Stop reason: complete", report)

    def test_missing_fresh_required_evidence_runs_bounded_follow_up(self) -> None:
        search_pipeline = SparseSearchPipeline()
        loop = ResearchLoop(
            search_pipeline=search_pipeline,
            planner=FreshPlanner(),
            max_iterations=2,
        )

        report = loop.run("test research", max_sources=8)

        self.assertEqual(
            search_pipeline.queries,
            [
                "required facts",
                "test research official recent primary source",
                "optional context",
            ],
        )
        self.assertIn("completed: 2", report)
        self.assertIn("blocked: 1", report)
        self.assertIn("Stop reason: complete", report)

    def test_missing_fresh_required_evidence_stops_at_max_iterations(self) -> None:
        search_pipeline = SparseSearchPipeline()
        loop = ResearchLoop(
            search_pipeline=search_pipeline,
            planner=FreshPlanner(),
            max_iterations=1,
        )

        report = loop.run("test research", max_sources=8)

        self.assertEqual(search_pipeline.queries, ["required facts"])
        self.assertIn("completed: 0", report)
        self.assertIn("blocked: 1", report)
        self.assertIn("Stop reason: max_iterations", report)

    def test_missing_non_fresh_required_evidence_does_not_run_fresh_follow_up(self) -> None:
        search_pipeline = SparseSearchPipeline()
        loop = ResearchLoop(
            search_pipeline=search_pipeline,
            planner=FakePlanner(),
            max_iterations=2,
        )

        report = loop.run("test research", max_sources=8)

        self.assertEqual(search_pipeline.queries, ["required facts"])
        self.assertNotIn("official recent primary source", " ".join(search_pipeline.queries))
        self.assertIn("blocked: 1", report)


if __name__ == "__main__":
    unittest.main()
