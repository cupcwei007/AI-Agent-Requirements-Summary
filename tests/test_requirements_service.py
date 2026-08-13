import json
import os
import subprocess
import sys

from requirements_agent.models import SourceDocument
from requirements_agent.service import RequirementsService
from requirements_agent.store import SQLiteStore
from requirements_agent.text import chunk_text, tokens


def document(tenant: str = "acme", principals: tuple[str, ...] = ("user:alice",)):
    return SourceDocument(
        tenant_id=tenant,
        external_id="PROJ-123",
        title="订单部分退款",
        text="用户可以对订单发起部分退款。\n\n该需求优先级为 P1。",
        source_type="jira",
        source_url="https://jira.example/browse/PROJ-123",
        allowed_principals=principals,
        metadata={"priority": "P1", "status": "review"},
    )


def test_mixed_language_tokenization_and_bounded_chunking():
    assert "部分" in tokens("支持部分 Refund")
    assert "refund" in tokens("支持部分 Refund")
    assert all(len(part) <= 120 for part in chunk_text("需求" * 150, max_chars=120, overlap=20))


def test_ingest_is_idempotent_but_acl_changes_are_applied():
    store = SQLiteStore()
    service = RequirementsService(store)
    assert service.ingest(document()) is True
    assert service.ingest(document(principals=("user:bob",))) is False
    assert service.answer(tenant_id="acme", principals=["user:alice"], question="部分退款").insufficient_evidence
    assert not service.answer(tenant_id="acme", principals=["user:bob"], question="部分退款").insufficient_evidence


def test_search_is_tenant_acl_and_metadata_scoped():
    service = RequirementsService(SQLiteStore())
    service.ingest(document())
    service.ingest(document(tenant="other"))

    allowed = service.answer(
        tenant_id="acme", principals=["user:alice"], question="订单退款",
        filters={"priority": "P1"},
    )
    assert not allowed.insufficient_evidence
    assert allowed.citations[0].external_id == "PROJ-123"
    assert "PROJ-123" in allowed.citations[0].source_url

    assert service.answer(
        tenant_id="acme", principals=["user:mallory"], question="订单退款"
    ).insufficient_evidence
    assert service.answer(
        tenant_id="acme", principals=["user:alice"], question="订单退款",
        filters={"priority": "P0"},
    ).insufficient_evidence


def test_no_evidence_returns_explicit_refusal_without_citations():
    service = RequirementsService(SQLiteStore())
    service.ingest(document())
    answer = service.answer(
        tenant_id="acme", principals=["user:alice"], question="登录验证码"
    )
    assert answer.insufficient_evidence is True
    assert answer.citations == ()
    assert "没有找到" in answer.text


def test_cli_json_exposes_citations(tmp_path):
    database = tmp_path / "requirements.db"
    environment = {**os.environ, "PYTHONPATH": "src"}
    subprocess.run(
        [sys.executable, "-m", "requirements_agent.cli", "--database", str(database),
         "ingest-json", "examples/jira_requirement.json"],
        check=True, env=environment, capture_output=True, text=True,
    )
    result = subprocess.run(
        [sys.executable, "-m", "requirements_agent.cli", "--database", str(database),
         "ask", "--tenant", "demo", "--principal", "user:alice", "--json", "部分退款"],
        check=True, env=environment, capture_output=True, text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["insufficient_evidence"] is False
    assert payload["citations"][0]["external_id"] == "PAY-123"
    assert payload["citations"][0]["source_url"].endswith("PAY-123")
