from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class RagConfig:
    enabled: bool
    max_files_per_request: int
    max_bytes_per_file: int
    max_total_attachment_bytes: int
    max_indexed_chunks: int
    max_retrieved_chunks: int
    max_context_chars: int
    chunk_target_chars: int
    chunk_overlap_chars: int
    safe_roots: tuple[str, ...]
    supported_extensions: tuple[str, ...]

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> "RagConfig":
        return cls(
            enabled=bool(settings["enabled"]),
            max_files_per_request=int(settings["max_files_per_request"]),
            max_bytes_per_file=int(settings["max_bytes_per_file"]),
            max_total_attachment_bytes=int(settings["max_total_attachment_bytes"]),
            max_indexed_chunks=int(settings["max_indexed_chunks"]),
            max_retrieved_chunks=int(settings["max_retrieved_chunks"]),
            max_context_chars=int(settings["max_context_chars"]),
            chunk_target_chars=int(settings["chunk_target_chars"]),
            chunk_overlap_chars=int(settings["chunk_overlap_chars"]),
            safe_roots=tuple(str(root) for root in settings["safe_roots"]),
            supported_extensions=tuple(str(ext).lower() for ext in settings["supported_extensions"])
        )
    
@dataclass(frozen=True)
class FileMention:
    raw: str
    path_text: str
    start: int
    end: int

@dataclass(frozen=True)
class Document:
    id: str
    name: str
    path: str
    content_hash: str
    byte_size: int
    text_length: int

@dataclass(frozen=True)
class Chunk:
    id: str
    document_id: str
    document_name: str
    index: int
    text: str

    @property
    def citation(self) -> str:
        return f"[file:{self.document_name}#chunk-{self.index}]"
    
@dataclass(frozen=True)
class RetrievedChunk:
    chunk: Chunk
    score: float

@dataclass(frozen=True)
class FileStatus:
    name: str
    status: str
    reason: str = ""
    chunks: int = 0

@dataclass
class IngestResult:
    statuses: list[FileStatus] = field(default_factory=list)
    documents: list[Document] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)