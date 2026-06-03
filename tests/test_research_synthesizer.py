import unittest
from unittest.mock import patch

from tools.research.models import ResearchEvidence, ResearchPlan, ResearchReport, ResearchSubquery
from tools.research.synthesizer import ResearchSynthesizer
from tools.search.models import EvidenceItem, EvidencePack, SearchPlan


def search_plan() -> SearchPlan:
    return SearchPlan(
        original_query="query",
        question_type="research",
        queries=["query"],
    )


def research_plan() -> ResearchPlan:
    return ResearchPlan(
        original_query="compare GDP forecasts",
        question_type="comparison",
        subqueries=[
            ResearchSubquery("one", "first"),
            ResearchSubquery("two", "second"),
            ResearchSubquery("three", "third", required=False),
        ],
        freshness_sensitive=True,
        preferred_source_types=["official statistics"],
        ambiguity_notes=["GDP can mean nominal, PPP, growth, or per capita."],
    )


def evidence_item(subquery: ResearchSubquery, claims: list[EvidenceItem]) -> ResearchEvidence:
    return ResearchEvidence(
        subquery=subquery,
        pack=EvidencePack(
            plan=search_plan(),
            claims=claims,
            confidence="medium",
        ),
    )


class TestResearchSynthesizer(unittest.TestCase):
    def setUp(self):
        self.patcher = patch("core.llm.call_llm_once", side_effect=Exception("API offline"))
        self.mock_call = self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    def test_synthesizer_uses_llm_when_successful(self):
        self.mock_call.side_effect = None
        self.mock_call.return_value = (
            '{"short_answer": "LLM Short answer.", "key_findings": ["LLM Finding 1."], "details": "LLM Details.", "confidence": "high", "confidence_reason": "Good sources", "caveats": ["LLM Caveat."]}',
            10
        )
        
        plan = research_plan()
        evidence = [
            evidence_item(
                plan.subqueries[0],
                [
                    EvidenceItem("Official data point.", "https://www.imf.org/report", "IMF", "fake")
                ]
            )
        ]
        
        report = ResearchSynthesizer().synthesize(plan, evidence)
        
        self.assertEqual(report.answer, "LLM Short answer.")
        self.assertEqual(report.key_findings, ["LLM Finding 1."])
        self.assertEqual(report.details, "LLM Details.")
        self.assertEqual(report.confidence, "high (Good sources)")
        self.assertEqual(report.caveats, ["LLM Caveat."])

    def test_synthesizer_dedupes_sources(self):
        plan = research_plan()
        evidence = [
            evidence_item(
                plan.subqueries[0],
                [
                    EvidenceItem("Claim one.", "https://example.com/one", "One", "fake"),
                    EvidenceItem("Claim duplicate source.", "https://example.com/one", "One", "fake"),
                ],
            ),
            evidence_item(
                plan.subqueries[1],
                [
                    EvidenceItem("Claim two.", "https://example.com/two", "Two", "fake"),
                ],
            ),
        ]

        report = ResearchSynthesizer().synthesize(plan, evidence)

        self.assertEqual(report.source_urls, ["https://example.com/one", "https://example.com/two"])

    def test_synthesizer_marks_forecasts_as_caveat(self):
        plan = research_plan()
        evidence = [
            evidence_item(
                plan.subqueries[0],
                [
                    EvidenceItem(
                        "The 2025 figure is a forecast, not final actual data.",
                        "https://www.imf.org/report",
                        "IMF report",
                        "fake",
                    )
                ],
            )
        ]

        report = ResearchSynthesizer().synthesize(plan, evidence)

        self.assertTrue(any("forecast" in caveat.casefold() for caveat in report.caveats))

    def test_synthesizer_renders_required_sections(self):
        plan = research_plan()
        evidence = [
            evidence_item(
                plan.subqueries[0],
                [
                    EvidenceItem(
                        "Official data gives a supported finding.",
                        "https://www.imf.org/report",
                        "IMF report",
                        "fake",
                    ),
                    EvidenceItem(
                        "A second source supports context.",
                        "https://www.reuters.com/markets/story",
                        "Reuters story",
                        "fake",
                    ),
                ],
            )
        ]

        report = ResearchSynthesizer().synthesize(plan, evidence)
        rendered = ResearchSynthesizer().render(report)

        self.assertIn("Short answer:", rendered)
        self.assertIn("Key findings:", rendered)
        self.assertIn("Details:", rendered)
        self.assertIn("Confidence:", rendered)
        self.assertIn("Caveats:", rendered)
        self.assertIn("Sources:", rendered)
        self.assertIn("https://www.imf.org/report", rendered)

    def test_synthesizer_low_confidence_without_sources(self):
        plan = research_plan()

        report = ResearchSynthesizer().synthesize(plan, [])

        self.assertEqual(report.confidence, "low")
        self.assertTrue(any("no source evidence" in caveat.casefold() for caveat in report.caveats))

    def test_synthesizer_renders_new_fields(self):
        plan = research_plan()
        report = ResearchReport(
            original_query=plan.original_query,
            question_type=plan.question_type,
            answer="Short answer context.",
            confidence="high",
            caveats=["Caveat text."],
            source_urls=["https://example.com/one"],
            key_findings=["Finding one.", "Finding two."],
            details="Detailed description paragraph here."
        )

        rendered = ResearchSynthesizer().render(report)

        self.assertIn("Short answer:\nShort answer context.", rendered)
        self.assertIn("Key findings:\n- Finding one.\n- Finding two.", rendered)
        self.assertIn("Details:\nDetailed description paragraph here.", rendered)

    def test_synthesizer_falls_back_when_llm_fails(self):
        plan = research_plan()
        evidence = [
            evidence_item(
                plan.subqueries[0],
                [
                    EvidenceItem("Official data point.", "https://www.imf.org/report", "IMF", "fake")
                ]
            )
        ]

        report = ResearchSynthesizer().synthesize(plan, evidence)

        self.assertIn("Official data point.", report.answer)
        self.assertListEqual(report.key_findings, [])
        self.assertEqual(report.details, "")


if __name__ == "__main__":
    unittest.main()