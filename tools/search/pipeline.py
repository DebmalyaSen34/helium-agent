from __future__ import annotations

import datetime as dt

from config.settings import SEARXNG_URL
from tools.search.builder import AnswerContextBuilder
from tools.search.extractor import EvidenceExtractor
from tools.search.fetcher import ContentFetcher
from tools.search.models import EvidencePack, FetchedPage
from tools.search.planner import SearchPlanner
from tools.search.providers import DdgsProvider, ProviderRunner, SearxngProvider
from tools.search.ranker import EvidenceRanker


class SearchPipeline:
    def __init__(
        self,
        provider_runner: ProviderRunner | None = None,
        fetcher: ContentFetcher | None = None,
        today: dt.date | None = None,
    ) -> None:
        self.today = today or dt.date.today()
        self.planner = SearchPlanner(today=self.today)
        self.provider_runner = provider_runner or ProviderRunner(
            [DdgsProvider(), SearxngProvider(SEARXNG_URL)],
            min_results=2,
        )
        self.fetcher = fetcher or ContentFetcher()
        self.extractor = EvidenceExtractor(today=self.today)
        self.ranker = EvidenceRanker()
        self.builder = AnswerContextBuilder()

    def collect(self, query: str, num_results: int = 5) -> EvidencePack:
        plan = self.planner.plan(query)
        results, provider_errors = self.provider_runner.search(plan.queries, limit=num_results)
        pages = self.fetcher.fetch(results)

        fetch_errors = [
            f"{page.url}: {page.error}"
            for page in pages
            if not page.ok and page.error
        ]

        matches, claims = self.extractor.extract(plan, pages)
        ranked_matches, ranked_claims = self.ranker.rank(plan, matches, claims)
        confidence, caveats = self._confidence_and_caveats(
            pages=pages,
            matches=ranked_matches,
            claims=ranked_claims,
            provider_errors=provider_errors,
            fetch_errors=fetch_errors,
        )

        return EvidencePack(
            plan=plan,
            results=results,
            pages=pages,
            matches=ranked_matches,
            claims=ranked_claims,
            provider_errors=provider_errors,
            fetch_errors=fetch_errors,
            answer=None,
            confidence=confidence,
            caveats=caveats,
        )

    def search(self, query: str, num_results: int = 5) -> str:
        return self.builder.build(self.collect(query, num_results=num_results))

    def _confidence_and_caveats(
        self,
        pages: list[FetchedPage],
        matches,
        claims,
        provider_errors: list[str],
        fetch_errors: list[str],
    ) -> tuple[str, list[str]]:
        evidence_count = len(matches) + len(claims)
        readable_pages = [page for page in pages if page.ok and page.text.strip()]
        caveats: list[str] = []

        if not pages:
            caveats.append("No search results were available from the configured providers.")
            return "low", caveats

        if provider_errors:
            caveats.append("Some search providers failed.")

        if fetch_errors:
            caveats.append("Some pages could not be fetched.")

        if not readable_pages:
            caveats.append("Search results were found, but no readable page text was available.")
            return "low", caveats

        if evidence_count >= 3:
            return "high", caveats

        if evidence_count >= 1:
            return "medium", caveats

        caveats.append("Search results were found, but no concise evidence could be extracted.")
        return "low", caveats


def search_web(query: str, num_results: int = 5) -> str:
    return SearchPipeline().search(query, num_results=num_results)