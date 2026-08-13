#!/usr/bin/env python3
"""Dependency-free local acceptance test for the current vertical slice."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {"PYTHONPATH": str(ROOT / "src")}


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "requirements_agent.cli", *arguments],
        cwd=ROOT,
        env=ENV,
        check=True,
        capture_output=True,
        text=True,
    )


def ask(database: Path, tenant: str, principal: str, question: str) -> dict:
    result = run(
        "--database", str(database), "ask", "--tenant", tenant,
        "--principal", principal, "--json", question,
    )
    return json.loads(result.stdout)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="requirements-agent-") as directory:
        database = Path(directory) / "acceptance.db"
        sample = ROOT / "examples" / "jira_requirement.json"

        first = json.loads(run(
            "--database", str(database), "ingest-json", str(sample)
        ).stdout)
        second = json.loads(run(
            "--database", str(database), "ingest-json", str(sample)
        ).stdout)
        assert first == {"changed": True}, "首次导入应写入内容"
        assert second == {"changed": False}, "重复导入必须幂等"

        allowed = ask(database, "demo", "user:alice", "哪些需求支持部分退款？")
        assert not allowed["insufficient_evidence"], "授权用户应检索到证据"
        assert allowed["citations"][0]["external_id"] == "PAY-123"
        assert allowed["citations"][0]["source_url"].endswith("PAY-123")

        unauthorized = ask(database, "demo", "user:mallory", "部分退款")
        other_tenant = ask(database, "other", "user:alice", "部分退款")
        unrelated = ask(database, "demo", "user:alice", "登录验证码")
        assert unauthorized["insufficient_evidence"], "ACL 必须阻止未授权用户"
        assert other_tenant["insufficient_evidence"], "租户之间必须隔离"
        assert unrelated["insufficient_evidence"], "无证据问题必须拒答"
        assert unauthorized["citations"] == unrelated["citations"] == []

    print("PASS: 7/7 acceptance checks passed")
    print("- first import and idempotent re-import")
    print("- authorized retrieval and source citation")
    print("- ACL isolation and tenant isolation")
    print("- explicit refusal with no citations when evidence is absent")


if __name__ == "__main__":
    main()
