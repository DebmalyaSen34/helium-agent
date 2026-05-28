from __future__ import annotations

from dataclasses import replace

from core.todo import TodoList
from tools.research.models import ResearchEvidence, ResearchPlan, ResearchSubquery
from tools.research.planner import ResearchPlanner
from tools.research.source_policy import SourcePolicy
from tools.research.synthesizer import ResearchSynthesizer
from tools.search.models import EvidencePack
from tools.search.pipeline import SearchPipeline


class ResearchLoop:
    def __init__(
        self,
        search_pipeline: SearchPipeline | None = None,
        planner: ResearchPlanner | None = None,
        synthesizer: ResearchSynthesizer | None = None,
        source_policy: SourcePolicy | None = None,
        max_iterations: int = 2,
    ) -> None:
        self.search_pipeline = search_pipeline or SearchPipeline()
        self.planner = planner or ResearchPlanner()
        self.source_policy = source_policy or SourcePolicy()
        self.synthesizer = synthesizer or ResearchSynthesizer(self.source_policy)
        self.max_iterations = max(1, max_iterations)

    def run(self, query: str, max_sources: int = 8) -> str:
        normalized = " ".join(query.strip().split())
        if not normalized:
            todos = TodoList()
            plan = self._empty_plan(query, max_sources=max_sources)
            return self._render_with_progress(plan, [], todos)

        plan = self.planner.plan(normalized, max_sources=max_sources)
        todos = TodoList()
        evidence: list[ResearchEvidence] = []
        selected_urls: set[str] = set()
        stop_reason = "complete"

        required_subqueries = [subquery for subquery in plan.subqueries if subquery.required]
        optional_subqueries = [subquery for subquery in plan.subqueries if not subquery.required]

        for subquery in required_subqueries:
            self._collect_subquery_evidence(
                plan=plan,
                subquery=subquery,
                todos=todos,
                evidence=evidence,
                selected_urls=selected_urls,
                max_sources=max_sources,
            )
            if len(selected_urls) >= max_sources:
                break

        if not self._coverage_sufficient(plan, required_subqueries, evidence):
            if self.max_iterations <= 1:
                stop_reason = "max_iterations"
            elif not plan.freshness_sensitive:
                stop_reason = "max_iterations"
            else:
                follow_up = ResearchSubquery(
                    query=self._follow_up_query(plan),
                    purpose="Find official recent primary source evidence.",
                    required=True,
                )
                self._collect_subquery_evidence(
                    plan=plan,
                    subquery=follow_up,
                    todos=todos,
                    evidence=evidence,
                    selected_urls=selected_urls,
                    max_sources=max_sources,
                    kind="research_follow_up",
                )
                if not self._coverage_sufficient(plan, required_subqueries, evidence):
                    stop_reason = "max_iterations"

        if stop_reason == "complete":
            for subquery in optional_subqueries:
                self._collect_subquery_evidence(
                    plan=plan,
                    subquery=subquery,
                    todos=todos,
                    evidence=evidence,
                    selected_urls=selected_urls,
                    max_sources=max_sources,
                )
                if len(selected_urls) >= max_sources:
                    break

        return self._render_with_progress(plan, evidence, todos, stop_reason=stop_reason)

    def _collect_subquery_evidence(
        self,
        plan: ResearchPlan,
        subquery: ResearchSubquery,
        todos: TodoList,
        evidence: list[ResearchEvidence],
        selected_urls: set[str],
        max_sources: int,
        kind: str = "research_subquery",
    ) -> None:
        todo = todos.add(
            title=subquery.query,
            kind=kind,
            notes=[subquery.purpose],
        )
        todos.start(todo.id)

        pack = self.search_pipeline.collect(subquery.query, num_results=5)
        trimmed_pack = self._trim_pack(pack, plan, selected_urls, max_sources=max_sources)

        if self._has_source_evidence(trimmed_pack):
            evidence.append(ResearchEvidence(subquery=subquery, pack=trimmed_pack))
            todos.complete(todo.id, note="Collected source evidence.")
        else:
            todos.block(todo.id, "No source evidence was available.")

    def _render_with_progress(
        self,
        plan: ResearchPlan,
        evidence: list[ResearchEvidence],
        todos: TodoList,
        stop_reason: str = "complete",
    ) -> str:
        report = self.synthesizer.synthesize(plan, evidence)
        rendered = self.synthesizer.render(report)
        return "\n".join(
            [
                rendered,
                "",
                "Research progress:",
                self._format_summary(todos.summary()),
                f"Stop reason: {stop_reason}",
            ]
        )

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

    def _ordered_subqueries(self, plan: ResearchPlan) -> list[ResearchSubquery]:
        required = [subquery for subquery in plan.subqueries if subquery.required]
        optional = [subquery for subquery in plan.subqueries if not subquery.required]
        return required + optional

    def _coverage_sufficient(
        self,
        plan: ResearchPlan,
        required_subqueries: list[ResearchSubquery],
        evidence: list[ResearchEvidence],
    ) -> bool:
        if not required_subqueries:
            return True

        evidenced_required_queries = {
            item.subquery.query for item in evidence if item.subquery in required_subqueries
        }
        if all(subquery.query in evidenced_required_queries for subquery in required_subqueries):
            return True

        return plan.freshness_sensitive and any(
            item.subquery.required
            and item.subquery.query == self._follow_up_query(plan)
            and self._has_source_evidence(item.pack)
            for item in evidence
        )

    def _follow_up_query(self, plan: ResearchPlan) -> str:
        return f"{plan.original_query} official recent primary source"

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

    def _format_summary(self, summary: dict[str, int]) -> str:
        return "\n".join(f"{key}: {value}" for key, value in summary.items())


__all__ = ["ResearchLoop"]
