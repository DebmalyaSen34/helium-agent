from __future__ import annotations

import datetime as dt
import re

from tools.search.models import EvidenceItem, FetchedPage, MatchEvidence, SearchPlan


TABLE_SCORE_RE = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})\s*\|\s*"
    r"(?P<home>[A-Za-z .'-]+?)\s*\|\s*"
    r"(?P<hg>\d+)\s*[-:]\s*(?P<ag>\d+)\s*\|\s*"
    r"(?P<away>[A-Za-z .'-]+)"
)

INLINE_SCORE_RE = re.compile(
    r"(?P<home>[A-Za-z .'-]+?)\s+"
    r"(?P<hg>\d+)\s*[-:]\s*(?P<ag>\d+)\s+"
    r"(?P<away>[A-Za-z .'-]+)"
)


class EvidenceExtractor:
    def __init__(self, today: dt.date | None = None) -> None:
        self.today = today or dt.date.today()

    def extract(
        self,
        plan: SearchPlan,
        pages: list[FetchedPage],
    ) -> tuple[list[MatchEvidence], list[EvidenceItem]]:
        if plan.question_type == "sports_recent_results":
            return self._extract_matches(plan, pages), []
        return [], self._extract_claims(pages)

    def _extract_matches(self, plan: SearchPlan, pages: list[FetchedPage]) -> list[MatchEvidence]:
        target_team = plan.target_team or ""
        matches: list[MatchEvidence] = []
        seen: set[tuple[str | None, str, str, int, int]] = set()

        for page in pages:
            if not page.ok:
                continue
            for line in page.text.splitlines():
                parsed = self._parse_match_line(line)
                if parsed is None:
                    continue
                date_text, home, home_goals, away_goals, away = parsed
                if target_team.casefold() not in {home.casefold(), away.casefold()}:
                    continue
                key = (date_text, home.casefold(), away.casefold(), home_goals, away_goals)
                if key in seen:
                    continue
                seen.add(key)
                matches.append(
                    MatchEvidence(
                        date=date_text,
                        home_team=home,
                        away_team=away,
                        home_goals=home_goals,
                        away_goals=away_goals,
                        competition=plan.competition,
                        url=page.url,
                        title=page.title,
                        source=page.source_result.provider,
                    )
                )
        return matches

    def _parse_match_line(self, line: str) -> tuple[str | None, str, int, int, str] | None:
        table_match = TABLE_SCORE_RE.search(line)
        if table_match:
            return (
                table_match.group("date"),
                self._clean_team(table_match.group("home")),
                int(table_match.group("hg")),
                int(table_match.group("ag")),
                self._clean_team(table_match.group("away")),
            )

        inline_match = INLINE_SCORE_RE.search(line)
        if inline_match:
            return (
                None,
                self._clean_team(inline_match.group("home")),
                int(inline_match.group("hg")),
                int(inline_match.group("ag")),
                self._clean_team(inline_match.group("away")),
            )
        return None

    def _clean_team(self, value: str) -> str:
        return " ".join(value.strip(" .-|").split())

    def _extract_claims(self, pages: list[FetchedPage]) -> list[EvidenceItem]:
        claims: list[EvidenceItem] = []
        for page in pages:
            if not page.ok:
                continue
            
            page_claims = 0
            sentences = re.split(r"(?<=[.!?])\s+", page.text)
            for sentence in sentences:
                sentence = " ".join(sentence.split())
                if len(sentence.split()) < 5:
                    continue
                
                # Skip sentences containing obvious navigation words
                lowered = sentence.lower()
                nav_indicators = ["main page", "current events", "terms of use", "create account", "log in", "privacy policy", "contact us"]
                if any(ind in lowered for ind in nav_indicators):
                    continue
                
                claims.append(
                    EvidenceItem(
                        claim=sentence,
                        url=page.url,
                        title=page.title,
                        source=page.source_result.provider,
                    )
                )
                page_claims += 1
                if page_claims >= 10:
                    break
        return claims
