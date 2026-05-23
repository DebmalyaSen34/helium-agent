from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from rag_service.models import Chunk, ExtractedDocument, PIPELINE_VERSION, SourceLocation


class RagCache:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.db_path = cache_dir / "rag_cache.sqlite3"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    file_hash TEXT PRIMARY KEY,
                    file_name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    text TEXT NOT NULL,
                    outline_json TEXT NOT NULL,
                    pipeline_version TEXT NOT NULL
                )
                """
            )
            connection.commit()
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chunks (
                    file_hash TEXT NOT NULL,
                    chunk_id TEXT PRIMARY KEY,
                    chunk_index INTEGER NOT NULL,
                    file_name TEXT NOT NULL,
                    text TEXT NOT NULL,
                    location_json TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    pipeline_version TEXT NOT NULL
                )
                """
            )

    def store(self, document: ExtractedDocument, chunks: list[Chunk]) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO documents
                (file_hash, file_name, file_path, byte_size, kind, text, outline_json, pipeline_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document.file_hash,
                    document.file_name,
                    document.file_path,
                    document.byte_size,
                    document.kind,
                    document.text,
                    json.dumps(list(document.outline)),
                    PIPELINE_VERSION,
                ),
            )
            connection.execute("DELETE FROM chunks WHERE file_hash = ?", (document.file_hash,))
            for chunk in chunks:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO chunks
                    (file_hash, chunk_id, chunk_index, file_name, text, location_json, strategy, pipeline_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document.file_hash,
                        chunk.id,
                        chunk.index,
                        chunk.file_name,
                        chunk.text,
                        json.dumps(chunk.location.__dict__),
                        chunk.strategy,
                        PIPELINE_VERSION,
                    ),
                )
            connection.commit()

    def load_chunks(self, file_hash: str) -> list[Chunk]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT chunk_id, chunk_index, file_name, text, location_json, strategy
                FROM chunks
                WHERE file_hash = ? AND pipeline_version = ?
                ORDER BY chunk_index
                """,
                (file_hash, PIPELINE_VERSION),
            ).fetchall()

        chunks: list[Chunk] = []
        for chunk_id, index, file_name, text, location_json, strategy in rows:
            chunks.append(
                Chunk(
                    id=chunk_id,
                    file_name=file_name,
                    file_hash=file_hash,
                    text=text,
                    location=SourceLocation(**json.loads(location_json)),
                    strategy=strategy,
                    index=index,
                )
            )
        return chunks

    def has_document(self, file_hash: str) -> bool:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT 1 FROM documents WHERE file_hash = ? AND pipeline_version = ?",
                (file_hash, PIPELINE_VERSION),
            ).fetchone()
        return row is not None
