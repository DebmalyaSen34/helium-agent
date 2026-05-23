from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


PIPELINE_VERSION = "rag-service-v1"


@dataclass(frozen=True)
class SourceLocation:
    kind: str
    label: str
    start_line: int | None = None
    end_line: int | None = None
    page: int | None = None
    sheet: str | None = None
    start_row: int | None = None
    end_row: int | None = None

    def display(self) -> str:
        if self.page is not None:
            return f"page {self.page}"
        if self.sheet:
            if self.start_row is not None and self.end_row is not None:
                return f'sheet "{self.sheet}" rows {self.start_row}-{self.end_row}'
            return f'sheet "{self.sheet}"'
        if self.start_line is not None and self.end_line is not None:
            return f"lines {self.start_line}-{self.end_line}"
        return self.label


@dataclass(frozen=True)
class ExtractedBlock:
    text: str
    location: SourceLocation
    title: str = ""


@dataclass(frozen=True)
class ExtractedDocument:
    file_path: str
    file_name: str
    file_hash: str
    byte_size: int
    kind: str
    text: str
    blocks: tuple[ExtractedBlock, ...]
    outline: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class Chunk:
    id: str
    file_name: str
    file_hash: str
    text: str
    location: SourceLocation
    strategy: str
    index: int

    @property
    def citation(self) -> str:
        location = self.location.display()
        return f"[file:{self.file_name}#chunk-{self.index} {location}]"


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float
    reason: str


@dataclass(frozen=True)
class EvidencePack:
    prompt: str
    sources: tuple[str, ...]
    citations: tuple[str, ...]
    warnings: tuple[str, ...] = ()
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRequest:
    question: str
    file_path: Path
    debug: bool = False


@dataclass(frozen=True)
class ValidationResult:
    file_path: Path
    byte_size: int


@dataclass(frozen=True)
class RagError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message
