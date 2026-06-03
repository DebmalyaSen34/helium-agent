from __future__ import annotations
from tools.research.models import ResearchEvidence, ResearchPlan, ResearchReport
from tools.research.source_policy import SourcePolicy
from tools.search.models import EvidenceItem, FetchedPage

class ResearchSynthesizer:
    def __init__(self, source_policy: SourcePolicy | None = None) -> None:
        self.source_policy = source_policy or SourcePolicy()

    def synthesize(self, plan: ResearchPlan, evidence: list[ResearchEvidence]) -> ResearchReport:
        from tools.research.models import ResearchReport

        findings = self._findings(evidence)
        source_urls = self._source_urls(evidence)
        caveats = self._caveats(plan, evidence, source_urls)
        confidence = self._confidence(source_urls, caveats)

        # Build fallback report first
        if findings:
            fallback_answer = "\n".join(f"- {finding}" for finding in findings[:8])
        else:
            fallback_answer = "No source evidence was available, so no supported research answer could be generated."

        fallback_report = ResearchReport(
            original_query=plan.original_query,
            question_type=plan.question_type,
            answer=fallback_answer,
            confidence=confidence,
            caveats=caveats,
            source_urls=source_urls,
            key_findings=[],
            details=""
        )

        if not evidence:
            return fallback_report

        # Try to synthesize using LLM
        try:
            from core.llm import call_llm_once
            import json
            import re

            source_mapping = {url: idx for idx, url in enumerate(source_urls, 1)}
            evidence_lines = []
            for item in evidence:
                evidence_lines.append(f"### Subquery: {item.subquery.query}")
                evidence_lines.append(f"Purpose: {item.subquery.purpose}")
                for claim in item.pack.claims[:5]:
                    idx = source_mapping.get(claim.url, "?")
                    evidence_lines.append(f"- Claim: {claim.claim} [Source: [{idx}] {claim.url}]")
                for page in item.pack.pages[:2]:
                    if page.ok and page.text:
                        idx = source_mapping.get(page.url, "?")
                        snippet = page.text.strip()[:600]
                        evidence_lines.append(f"- Snippet from '{page.title}': {snippet}... [Source: [{idx}] {page.url}]")

            sources_text = "\n".join(f"[{idx}] {url}" for url, idx in source_mapping.items())
            evidence_text = "\n".join(evidence_lines)

            prompt = f"""
You are a research synthesis module. Write a cited, high-quality, professional, and comprehensive research report based ONLY on the gathered evidence.

Original User Query:
{plan.original_query}

Preferred Source Types:
{plan.preferred_source_types}

Ambiguity Notes:
{plan.ambiguity_notes}

Sources List:
{sources_text}

Evidence Gathered:
{evidence_text}

Instructions:
1. Synthesize the evidence into a coherent, comprehensive, detailed in-depth report. Do not fabricate facts or sources outside the provided evidence.
2. In your writing, use citation markers like [1], [2] to reference the sources from the Sources List.
3. Keep the tone professional, objective, and analytical.
4. Output your response as a single valid JSON object matching the schema below. Do not include markdown formatting or extra text outside the JSON.

JSON Schema:
{{
  "short_answer": "A concise, comprehensive paragraph summarizing the core answer to the query.",
  "key_findings": [
    "A major finding with citation, e.g. [1].",
    "Another key finding..."
  ],
  "details": "An in-depth, detailed multi-paragraph breakdown of the findings, explaining nuances, comparisons, and background context with citations (e.g. [1], [2]). This section should be comprehensive, rich in information, and use markdown subheadings and bullet points for structural formatting to make it look highly professional and clear.",
  "confidence": "high | medium | low",
  "confidence_reason": "Brief reason for this confidence rating.",
  "caveats": [
    "A limitation, potential bias, or gap in the evidence...",
    "Another caveat..."
  ]
}}
""".strip()

            messages = [
                {
                    "role": "system",
                    "content": "You are a research synthesis module. Synthesize a coherent, factual, and cited report from search evidence.",
                },
                {"role": "user", "content": prompt},
            ]

            raw_reply, _ = call_llm_once(messages)
            text = raw_reply.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?", "", text, flags=re.IGNORECASE).strip()
                text = re.sub(r"```$", "", text).strip()

            first = text.find("{")
            last = text.rfind("}")
            if first != -1 and last != -1 and last > first:
                data = json.loads(text[first:last+1])
                
                # Extract structured fields
                short_answer = data.get("short_answer") or fallback_answer
                key_findings = data.get("key_findings") or []
                details = data.get("details") or short_answer
                
                raw_conf = data.get("confidence") or confidence
                conf_reason = data.get("confidence_reason")
                conf_text = f"{raw_conf} ({conf_reason})" if conf_reason else raw_conf
                
                rep_caveats = data.get("caveats") or caveats

                return ResearchReport(
                    original_query=plan.original_query,
                    question_type=plan.question_type,
                    answer=short_answer,
                    confidence=conf_text,
                    caveats=rep_caveats,
                    source_urls=source_urls,
                    key_findings=key_findings,
                    details=details
                )
        except Exception:
            pass

        return fallback_report
    
    def render(self, report: ResearchReport) -> str:
        lines = [
            f"# Research Report: {report.original_query}",
            "",
            "## Executive Summary",
            report.answer,
            "",
            "## Key Findings",
        ]

        if getattr(report, "key_findings", None):
            lines.extend(f"* {finding}" for finding in report.key_findings)
        else:
            if report.answer.startswith(("- ", "* ")):
                lines.extend(report.answer.splitlines())
            else:
                lines.append(f"* {report.answer}")

        details = getattr(report, "details", None) or report.answer
        lines.extend(
            [
                "",
                "## Detailed Analysis",
                details,
                "",
                "## Research Quality & Confidence",
                f"* **Confidence Level**: {report.confidence}",
            ]
        )

        if report.caveats:
            lines.append("* **Caveats & Limitations**:")
            lines.extend(f"  * {caveat}" for caveat in report.caveats)

        lines.extend(["", "## Sources"])
        if report.source_urls:
            lines.extend(f"{idx}. {url}" for idx, url in enumerate(report.source_urls, 1))
        else:
            lines.append("* No sources were available.")

        return "\n".join(lines)
    
    def _findings(self, evidence: list[ResearchEvidence]) -> list[str]:
        findings: list[str] = []
        seen: set[str] = set()

        for item in evidence:
            if item.pack.answer:
                self._append_unique(findings, seen, item.pack.answer)

            for claim in item.pack.claims[:3]:
                self._append_unique(findings, seen, claim.claim)

            if not item.pack.answer and not item.pack.claims:
                for page in item.pack.pages[:1]:
                    snippet = self._page_snippet(page)
                    if snippet:
                        self._append_unique(findings, seen, snippet)

        return findings
    
    def _source_urls(self, evidence: list[ResearchEvidence]) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()

        for item in evidence:
            for claim in item.pack.claims:
                self._append_unique(urls, seen, claim.url)

            for page in item.pack.pages:
                if page.ok:
                    self._append_unique(urls, seen, page.url)

            for result in item.pack.results:
                self._append_unique(urls, seen, result.url)

        return urls 
    
    def _caveats(self, plan: ResearchPlan, evidence: list[ResearchEvidence], source_urls: list[str]) -> list[str]:
        caveats: list[str] = []
        seen: set[str] = set()

        if not source_urls:
            self._append_unique(caveats, seen, "No source evidence was available.")

        if len(source_urls) == 1:
            self._append_unique(caveats, seen, "Only one distinct source was available.")

        for note in plan.ambiguity_notes:
            self._append_unique(caveats, seen, note)

        if plan.freshness_sensitive:
            self._append_unique(caveats, seen, "This query is freshness-sensitive; results may change quickly.")

        text_blob = " ".join(
            [
                plan.original_query,
                *plan.ambiguity_notes,
                *[
                    claim.claim
                    for item in evidence
                    for claim in item.pack.claims
                ],
                *[
                    item.pack.answer or ""
                    for item in evidence
                ],
            ]
        ).casefold()

        if "forecast" in text_blob or "estimate" in text_blob or "projection" in text_blob:
            self._append_unique(caveats, seen, "Some values may be forecasts, estimates, or projections rather than final actuals.")

        for item in evidence:
            for caveat in item.pack.caveats:
                self._append_unique(caveats, seen, caveat)
            if item.pack.provider_errors:
                self._append_unique(caveats, seen, "Some search providers failed.")
            if item.pack.fetch_errors:
                self._append_unique(caveats, seen, "Some pages could not be fetched.")

        if source_urls and not self._has_preferred_or_official_source(source_urls):
            self._append_unique(caveats, seen, "No clearly authoritative source was identified.")

        return caveats
    
    def _confidence(self, source_urls: list[str], caveats: list[str]) -> str:

        if not source_urls or len(source_urls) < 2:
            return "low"
        
        caveat_text = " ".join(caveats).casefold()
        if "no clarity authoritative" in caveat_text:
            return "low"
        
        if len(source_urls)>=3:
            return "high"
        
        return "medium"
    
    def _has_preferred_or_official_source(self, urls: list[str]) -> bool:
        labels = {self.source_policy.source_label(url) for url in urls}
        return bool(labels & {"official", "academic", "financial news", "reputable news", "primary company source"})
    
    def _page_snippet(self, page: FetchedPage) -> str:
        if not page.ok or not page.text.strip():
            return ""
        
        first_sentence = page.text.strip().split(". ", 1)[0].strip()
        if not first_sentence:
            return ""
        if not first_sentence.endswith((".", "!", "?")):
            first_sentence += "."
        return first_sentence
    
    def _append_unique(self, values: list[str], seen: set[str], value: str) -> None:
        normalized = " ".join(value.strip().split())
        if not normalized:
            return
        key = normalized.casefold()
        if key in seen:
            return
        seen.add(key)
        values.append(normalized)

    def _append_url(self, urls: list[str], seen: set[str], url: str) -> None:
        normalized = url.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        urls.append(normalized)