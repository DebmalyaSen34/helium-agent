from __future__ import annotations

from dataclasses import replace

from tools.research.classifier import ResearchClassifier
from tools.research.models import ResearchEvidence, ResearchPlan, ResearchSubquery
from tools.research.planner import ResearchPlanner
from tools.research.source_policy import SourcePolicy
from tools.research.synthesizer import ResearchSynthesizer
from tools.search.models import EvidenceItem, EvidencePack, FetchedPage, SearchResult
from tools.search.pipeline import SearchPipeline


class ResearchPipeline:
    def __init__(
        self,
        search_pipeline: SearchPipeline | None = None,
        classifier: ResearchClassifier | None = None,
        planner: ResearchPlanner | None = None,
        synthesizer: ResearchSynthesizer | None = None,
        source_policy: SourcePolicy | None = None,
    ) -> None:
        self.search_pipeline = search_pipeline or SearchPipeline()
        self.classifier = classifier or ResearchClassifier()
        self.planner = planner or ResearchPlanner()
        self.source_policy = source_policy or SourcePolicy()
        self.synthesizer = synthesizer or ResearchSynthesizer(self.source_policy)

    def run(self, query: str, max_sources: int = 8) -> str:
        from tools.research.loop import ResearchLoop

        loop = ResearchLoop(
            search_pipeline=self.search_pipeline,
            planner=self.planner,
            synthesizer=self.synthesizer,
            source_policy=self.source_policy,
        )
        return loop.run(query, max_sources=max_sources)

    def _collect_evidence(self, plan: ResearchPlan, max_sources: int) -> list[ResearchEvidence]:
        research_evidence: list[ResearchEvidence] = []
        selected_urls: set[str] = set()

        for subquery in plan.subqueries:
            pack = self.search_pipeline.collect(subquery.query, num_results=5)
            trimmed_pack = self._trim_pack(pack, plan, selected_urls, max_sources=max_sources)

            if self._has_source_evidence(trimmed_pack):
                research_evidence.append(
                    ResearchEvidence(
                        subquery=subquery,
                        pack=trimmed_pack,
                    )
                )

            if len(selected_urls) >= max_sources:
                break

        return research_evidence

    def _trim_pack(
        self,
        pack: EvidencePack,
        plan: ResearchPlan,
        selected_urls: set[str],
        max_sources: int,
    ) -> EvidencePack:
        allowed_urls = self._rank_pack_urls(pack, plan)
        remaining_slots = max_sources - len(selected_urls)

        if remaining_slots <= 0:
            return replace(pack, results=[], pages=[], claims=[])

        chosen_urls: set[str] = set()
        for url in allowed_urls:
            if url in selected_urls:
                continue
            chosen_urls.add(url)
            selected_urls.add(url)
            if len(chosen_urls) >= remaining_slots:
                break

        return replace(
            pack,
            results=[result for result in pack.results if result.url in chosen_urls],
            pages=[page for page in pack.pages if page.url in chosen_urls],
            claims=[claim for claim in pack.claims if claim.url in chosen_urls],
        )

    def _rank_pack_urls(self, pack: EvidencePack, plan: ResearchPlan) -> list[str]:
        urls = self._pack_urls(pack)

        return sorted(
            urls,
            key=lambda url: self.source_policy.score_url(url, plan.preferred_source_types),
            reverse=True,
        )

    def _pack_urls(self, pack: EvidencePack) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()

        for claim in pack.claims:
            self._append_url(urls, seen, claim.url)

        for page in pack.pages:
            if page.ok:
                self._append_url(urls, seen, page.url)

        for result in pack.results:
            self._append_url(urls, seen, result.url)

        return urls

    def _has_source_evidence(self, pack: EvidencePack) -> bool:
        return bool(pack.results or pack.pages or pack.claims)

    def _append_url(self, urls: list[str], seen: set[str], url: str) -> None:
        normalized = url.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        urls.append(normalized)

    def _empty_plan(self, query: str, max_sources: int) -> ResearchPlan:
        return ResearchPlan(
            original_query=query,
            question_type="general_research",
            subqueries=[
                ResearchSubquery(
                    query=query,
                    purpose="No query was available.",
                )
            ],
            freshness_sensitive=False,
            max_sources=max_sources,
        )


def research_query(query: str, max_sources: int = 8) -> str:
    return ResearchPipeline().run(query, max_sources=max_sources)