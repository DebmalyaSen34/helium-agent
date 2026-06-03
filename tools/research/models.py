from __future__ import annotations
from dataclasses import dataclass, field
from tools.search.models import EvidencePack

@dataclass(frozen=True)
class ResearchSubquery:
    query: str
    purpose: str
    required: bool = True

@dataclass(frozen=True)
class ResearchPlan:
    original_query: str
    question_type: str
    subqueries: list[ResearchSubquery]
    freshness_sensitive: bool
    preferred_source_types: list[str] = field(default_factory=list)
    ambiguity_notes: list[str] = field(default_factory=list)
    max_sources: int = 8

@dataclass(frozen=True)
class ResearchEvidence:
    subquery: ResearchSubquery
    pack: EvidencePack

@dataclass(frozen=True)
class ResearchReport:
    original_query: str
    question_type: str
    answer: str
    confidence: str
    caveats: list[str]
    source_urls: list[str]
    key_findings: list[str] = field(default_factory=list)
    details: str = ""