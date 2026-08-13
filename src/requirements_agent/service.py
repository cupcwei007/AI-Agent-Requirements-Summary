"""Application service enforcing evidence-backed answers."""

from __future__ import annotations

from collections.abc import Iterable

from .models import Answer, SourceDocument
from .store import SQLiteStore


class RequirementsService:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def ingest(self, document: SourceDocument) -> bool:
        return self.store.upsert(document)

    def answer(
        self,
        *,
        tenant_id: str,
        principals: Iterable[str],
        question: str,
        filters: dict[str, str] | None = None,
    ) -> Answer:
        hits = self.store.search(
            tenant_id=tenant_id,
            principals=principals,
            query=question,
            filters=filters,
        )
        if not hits:
            return Answer(
                text="没有找到当前权限范围内足以回答该问题的资料。",
                citations=(),
                insufficient_evidence=True,
            )
        # The first vertical slice deliberately returns extractive evidence. A model
        # adapter can later synthesize it, but citations must remain this allow-list.
        lines = [f"找到 {len(hits)} 条相关证据："]
        lines.extend(
            f"- {hit.title}：{hit.text[:240]} [{hit.chunk_id}]" for hit in hits
        )
        return Answer(text="\n".join(lines), citations=tuple(hits), insufficient_evidence=False)
