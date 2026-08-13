"""SQLite persistence with mandatory tenant and principal filtering."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from .models import SearchHit, SourceDocument
from .text import chunk_text, tokens


class SQLiteStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    def _migrate(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sources (
                tenant_id TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_url TEXT NOT NULL,
                metadata TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (tenant_id, external_id)
            );
            CREATE TABLE IF NOT EXISTS source_acl (
                tenant_id TEXT NOT NULL,
                external_id TEXT NOT NULL,
                principal TEXT NOT NULL,
                PRIMARY KEY (tenant_id, external_id, principal),
                FOREIGN KEY (tenant_id, external_id)
                    REFERENCES sources (tenant_id, external_id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                external_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                body TEXT NOT NULL,
                token_set TEXT NOT NULL,
                FOREIGN KEY (tenant_id, external_id)
                    REFERENCES sources (tenant_id, external_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_scope
                ON chunks (tenant_id, external_id);
            """
        )

    def upsert(self, document: SourceDocument) -> bool:
        """Insert or replace a document. Return False when its content is unchanged."""
        if not document.tenant_id or not document.external_id:
            raise ValueError("tenant_id and external_id are required")
        if not document.allowed_principals:
            raise ValueError("at least one allowed principal is required")
        digest = hashlib.sha256(
            (document.title + "\0" + document.text).encode()
        ).hexdigest()
        existing = self.connection.execute(
            "SELECT content_hash FROM sources WHERE tenant_id=? AND external_id=?",
            (document.tenant_id, document.external_id),
        ).fetchone()
        content_changed = existing is None or existing["content_hash"] != digest
        with self.connection:
            self.connection.execute(
                """INSERT INTO sources VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, external_id) DO UPDATE SET
                    title=excluded.title, body=excluded.body,
                    source_type=excluded.source_type, source_url=excluded.source_url,
                    metadata=excluded.metadata, content_hash=excluded.content_hash,
                    updated_at=excluded.updated_at""",
                (
                    document.tenant_id, document.external_id, document.title,
                    document.text, document.source_type, document.source_url,
                    json.dumps(document.metadata, ensure_ascii=False), digest,
                    document.updated_at,
                ),
            )
            self.connection.execute(
                "DELETE FROM source_acl WHERE tenant_id=? AND external_id=?",
                (document.tenant_id, document.external_id),
            )
            self.connection.executemany(
                "INSERT INTO source_acl VALUES (?, ?, ?)",
                ((document.tenant_id, document.external_id, principal)
                 for principal in sorted(set(document.allowed_principals))),
            )
            if content_changed:
                self.connection.execute(
                    "DELETE FROM chunks WHERE tenant_id=? AND external_id=?",
                    (document.tenant_id, document.external_id),
                )
                chunks = chunk_text(document.text)
                self.connection.executemany(
                    "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        (
                            f"{document.tenant_id}:{document.external_id}:{position}",
                            document.tenant_id, document.external_id, position, body,
                            json.dumps(sorted(tokens(document.title + " " + body))),
                        )
                        for position, body in enumerate(chunks)
                    ),
                )
        return content_changed

    def search(
        self,
        *,
        tenant_id: str,
        principals: Iterable[str],
        query: str,
        limit: int = 8,
        filters: dict[str, str] | None = None,
    ) -> list[SearchHit]:
        if limit < 1 or limit > 50:
            raise ValueError("limit must be between 1 and 50")
        principal_list = sorted(set(principals))
        if not principal_list:
            return []
        placeholders = ",".join("?" for _ in principal_list)
        rows = self.connection.execute(
            f"""SELECT DISTINCT c.id, c.body, c.token_set, s.external_id,
                       s.title, s.source_url, s.metadata
                FROM chunks c
                JOIN sources s ON s.tenant_id=c.tenant_id
                    AND s.external_id=c.external_id
                JOIN source_acl a ON a.tenant_id=s.tenant_id
                    AND a.external_id=s.external_id
                WHERE c.tenant_id=? AND a.principal IN ({placeholders})""",
            [tenant_id, *principal_list],
        ).fetchall()
        query_tokens = tokens(query)
        if not query_tokens:
            return []
        hits: list[SearchHit] = []
        for row in rows:
            metadata = json.loads(row["metadata"])
            if filters and any(str(metadata.get(key)) != value for key, value in filters.items()):
                continue
            candidate = set(json.loads(row["token_set"]))
            intersection = query_tokens & candidate
            if not intersection:
                continue
            # Weighted coverage rewards exact query coverage while mildly preferring
            # focused chunks. This deterministic score is the MVP lexical baseline.
            score = len(intersection) / len(query_tokens) + 0.1 * len(intersection) / len(candidate)
            hits.append(
                SearchHit(
                    chunk_id=row["id"], external_id=row["external_id"],
                    title=row["title"], text=row["body"],
                    source_url=row["source_url"], metadata=metadata, score=score,
                )
            )
        return sorted(hits, key=lambda hit: (-hit.score, hit.chunk_id))[:limit]

    def close(self) -> None:
        self.connection.close()
