import unittest
from unittest.mock import patch

from tools.research.models import ResearchPlan, ResearchSubquery
from tools.research.pipeline import ResearchPipeline
from tools.research.synthesizer import ResearchSynthesizer
from tools.search.models import EvidenceItem, EvidencePack, FetchedPage, SearchPlan, SearchResult


class FakePlanner:
    def plan(self, query: str, max_sources: int = 8) -> ResearchPlan:
        return ResearchPlan(
            original_query=query,
            question_type="comparison",
            subqueries=[
                ResearchSubquery("query one", "Find first evidence"),
                ResearchSubquery("query two", "Find second evidence"),
                ResearchSubquery("query three", "Cross-check", required=False),
            ],
            freshness_sensitive=True,
            preferred_source_types=["official statistics", "reputable financial news"],
            ambiguity_notes=["Metric may be ambiguous."],
            max_sources=max_sources,
        )


class FakeSearchPipeline:
    def collect(self, query: str, num_results: int = 5) -> EvidencePack:
        url = {
            "query one": "https://www.imf.org/report",
            "query two": "https://www.reuters.com/markets/story",
            "query three": "https://source.example/report",
        }[query]

        result = SearchResult(
            title=f"Title for {query}",
            url=url,
            snippet="snippet",
            provider="fake",
            rank=1,
            query=query,
        )

        return EvidencePack(
            plan=SearchPlan(
                original_query=query,
                question_type="research",
                queries=[query],
            ),
            results=[result],
            pages=[
                FetchedPage(
                    url=url,
                    title=result.title,
                    text=f"{query} has useful evidence.",
                    source_result=result,
                )
            ],
            claims=[
                EvidenceItem(
                    claim=f"{query} supported finding.",
                    url=url,
                    title=result.title,
                    source="fake",
                )
            ],
            confidence="medium",
        )


class FakeEmptySearchPipeline:
    def collect(self, query: str, num_results: int = 5) -> EvidencePack:
        return EvidencePack(
            plan=SearchPlan(
                original_query=query,
                question_type="research",
                queries=[query],
            ),
            results=[],
            pages=[],
            claims=[],
            confidence="low",
            caveats=["No source evidence was available."],
        )


class TestResearchPipeline(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("core.llm.call_llm_once", side_effect=Exception("API offline"))
        self.mock_call = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_research_pipeline_returns_cited_report(self):
        pipeline = ResearchPipeline(
            search_pipeline=FakeSearchPipeline(),
            planner=FakePlanner(),
            synthesizer=ResearchSynthesizer(),
        )

        report = pipeline.run("compare India and China GDP in 2025")

        self.assertIn("## Executive Summary", report)
        self.assertIn("## Key Findings", report)
        self.assertIn("## Sources", report)
        self.assertIn("## Research Quality & Confidence", report)
        self.assertIn("https://www.imf.org/report", report)
        self.assertIn("https://www.reuters.com/markets/story", report)

    def test_research_pipeline_limits_sources(self):
        pipeline = ResearchPipeline(
            search_pipeline=FakeSearchPipeline(),
            planner=FakePlanner(),
            synthesizer=ResearchSynthesizer(),
        )

        report = pipeline.run("compare India and China GDP in 2025", max_sources=2)

        self.assertIn("https://www.imf.org/report", report)
        self.assertIn("https://www.reuters.com/markets/story", report)
        self.assertNotIn("https://source.example/report", report)

    def test_research_pipeline_reports_low_confidence_without_sources(self):
        pipeline = ResearchPipeline(
            search_pipeline=FakeEmptySearchPipeline(),
            planner=FakePlanner(),
            synthesizer=ResearchSynthesizer(),
        )

        report = pipeline.run("Why is Indian Rupee falling recently?")

        self.assertIn("## Research Quality & Confidence", report)
        self.assertIn("low", report.casefold())
        self.assertIn("no source evidence", report.casefold())

    def test_research_query_public_api_uses_loop_report(self):
        pipeline = ResearchPipeline(
            search_pipeline=FakeSearchPipeline(),
            planner=FakePlanner(),
            synthesizer=ResearchSynthesizer(),
        )

        report = pipeline.run("compare India and China GDP in 2025")

        self.assertIn("Research progress:", report)
        self.assertIn("Stop reason:", report)


if __name__ == "__main__":
    unittest.main()
