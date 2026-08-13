"""Small CLI for exercising the first end-to-end slice."""

from __future__ import annotations

import argparse
import json

from .models import SourceDocument
from .service import RequirementsService
from .store import SQLiteStore


def main() -> None:
    parser = argparse.ArgumentParser(prog="requirements-agent")
    parser.add_argument("--database", default="requirements.db")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest-json")
    ingest.add_argument("file")
    ask = subparsers.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--tenant", required=True)
    ask.add_argument("--principal", action="append", required=True)
    ask.add_argument(
        "--json", action="store_true", help="output answer and citations as JSON"
    )
    args = parser.parse_args()

    store = SQLiteStore(args.database)
    service = RequirementsService(store)
    try:
        if args.command == "ingest-json":
            with open(args.file, encoding="utf-8") as handle:
                payload = json.load(handle)
            changed = service.ingest(SourceDocument(**payload))
            print(json.dumps({"changed": changed}))
        else:
            answer = service.answer(
                tenant_id=args.tenant,
                principals=args.principal,
                question=args.question,
            )
            if args.json:
                print(json.dumps(
                    {
                        "answer": answer.text,
                        "insufficient_evidence": answer.insufficient_evidence,
                        "citations": [
                            {
                                "chunk_id": hit.chunk_id,
                                "external_id": hit.external_id,
                                "title": hit.title,
                                "text": hit.text,
                                "source_url": hit.source_url,
                                "metadata": hit.metadata,
                                "score": hit.score,
                            }
                            for hit in answer.citations
                        ],
                    },
                    ensure_ascii=False,
                ))
            else:
                print(answer.text)
    finally:
        store.close()


if __name__ == "__main__":
    main()
