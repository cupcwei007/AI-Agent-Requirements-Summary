"""Domain models shared by ingestion and retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class SourceDocument:
    tenant_id: str
    external_id: str
    title: str
    text: str
    source_type: str
    source_url: str
    allowed_principals: tuple[str, ...]
    metadata: dict[str, str] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


@dataclass(frozen=True, slots=True)
class SearchHit:
    chunk_id: str
    external_id: str
    title: str
    text: str
    source_url: str
    metadata: dict[str, str]
    score: float


@dataclass(frozen=True, slots=True)
class Answer:
    text: str
    citations: tuple[SearchHit, ...]
    insufficient_evidence: bool
