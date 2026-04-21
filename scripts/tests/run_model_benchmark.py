from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "temp" / "model-benchmark"


@dataclass
class BenchmarkCase:
    id: str
    question: str
    scope_name_contains: str | None = None
    scope_provider: str | None = None
    expected_groups: list[list[str]] | None = None
    notes: str = ""


@dataclass
class ModelCaseResult:
    model: str
    case_id: str
    passed: bool
    latency_ms: float
    reply: str
    matched_groups: int
    total_groups: int
    document_id: str | None = None


CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        id="starter-safe-mode",
        question="Vad gör safe mode i Local AI OS?",
        expected_groups=[
            ["safe mode", "säkert läge", "säker läge"],
            ["block", "blockerar", "stops", "blocks", "spärr"],
            ["admin", "administrativa", "risk", "riskfyllda", "högrisk"],
        ],
        notes="General product/admin behavior from starter knowledge.",
    ),
    BenchmarkCase(
        id="starter-settings",
        question="Vad innehåller Settings i Local AI OS?",
        expected_groups=[
            ["settings", "kontrollpanel", "admin"],
            ["overview", "översikt"],
            ["runtime"],
            ["connector", "connectors"],
            ["security", "säker"],
        ],
        notes="General settings understanding from starter knowledge.",
    ),
    BenchmarkCase(
        id="starter-login",
        question="Hur loggar man in i Local AI OS?",
        expected_groups=[
            ["login", "logga in", "sign in", "/login"],
            ["admin", "viewer", "konto", "användare", "username"],
        ],
        notes="Login/helpfulness check from starter knowledge.",
    ),
    BenchmarkCase(
        id="sharepoint-docx",
        question="What is the policy title?",
        scope_name_contains="policy",
        scope_provider="sharepoint",
        expected_groups=[["retention policy aurora"]],
        notes="Grounded DOCX retrieval.",
    ),
    BenchmarkCase(
        id="sharepoint-xlsx",
        question="What is the Q2 total value in this spreadsheet?",
        scope_name_contains="metrics",
        scope_provider="sharepoint",
        expected_groups=[["982"]],
        notes="Grounded spreadsheet retrieval.",
    ),
    BenchmarkCase(
        id="sharepoint-pptx",
        question="What milestone name appears in this presentation?",
        scope_name_contains="roadmap",
        scope_provider="sharepoint",
        expected_groups=[["orion launch"]],
        notes="Grounded presentation retrieval.",
    ),
    BenchmarkCase(
        id="sharepoint-pdf",
        question="What incident code appears in the scanned PDF?",
        scope_name_contains="scan-pdf",
        scope_provider="sharepoint",
        expected_groups=[["inc-2048", "inc 2048"]],
        notes="Grounded OCR PDF retrieval.",
    ),
    BenchmarkCase(
        id="drive-docx",
        question="Vad handlar det här dokumentet främst om?",
        scope_name_contains="cykelstölder",
        scope_provider="google_drive",
        expected_groups=[
            ["register"],
            ["cykelstöld", "cykelstölder", "bike theft", "theft"],
        ],
        notes="Grounded Google Drive document understanding.",
    ),
]


class BenchmarkFailure(RuntimeError):
    pass


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _normalize(text: str) -> str:
    return " ".join(text.lower().replace("-", " ").split())


def _match_groups(text: str, groups: list[list[str]]) -> tuple[int, int]:
    normalized = _normalize(text)
    matched = 0
    for group in groups:
        if any(_normalize(term) in normalized for term in group):
            matched += 1
    return matched, len(groups)


def _ensure_ok(response: requests.Response, context: str) -> dict[str, Any]:
    if not response.ok:
        raise BenchmarkFailure(f"{context} failed: {response.status_code} {response.text[:500]}")
    if not response.content:
        return {}
    return response.json()


def _login(session: requests.Session, base_url: str, username: str, password: str) -> None:
    response = session.post(
        f"{base_url}/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    _ensure_ok(response, "login")


def _load_documents(session: requests.Session, base_url: str) -> list[dict[str, Any]]:
    payload = _ensure_ok(
        session.get(f"{base_url}/documents", params={"limit": 500, "offset": 0}, timeout=60),
        "list documents",
    )
    return payload.get("documents", [])


def _find_document_id(documents: list[dict[str, Any]], case: BenchmarkCase) -> str | None:
    if not case.scope_name_contains:
        return None
    needle = case.scope_name_contains.lower()
    for document in documents:
        if case.scope_provider and document.get("source_provider") != case.scope_provider:
            continue
        if document.get("processing_status") != "processed":
            continue
        if document.get("indexing_status") != "indexed":
            continue
        name = str(document.get("original_name", "")).lower()
        title = str(document.get("document_title", "")).lower()
        if needle in name or needle in title:
            return str(document["id"])
    return None


def _ask(
    session: requests.Session,
    base_url: str,
    *,
    model: str,
    question: str,
    document_id: str | None,
) -> tuple[float, dict[str, Any]]:
    payload: dict[str, Any] = {
        "message": question,
        "model": model,
        "persist_conversation": False,
    }
    if document_id:
        payload["document_ids"] = [document_id]
    started = time.perf_counter()
    response = session.post(f"{base_url}/chat", json=payload, timeout=300)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, _ensure_ok(response, f"chat {model}")


def _write_markdown(path: Path, metadata: dict[str, Any], rows: list[ModelCaseResult]) -> None:
    lines = [
        "# Model Benchmark Report",
        "",
        f"- Timestamp: {metadata['timestamp']}",
        f"- Base URL: {metadata['base_url']}",
        f"- Models: {', '.join(metadata['models'])}",
        "",
        "## Results",
        "",
    ]

    for case_id in metadata["case_order"]:
        lines.append(f"### {case_id}")
        case_rows = [row for row in rows if row.case_id == case_id]
        for row in case_rows:
            status = "PASS" if row.passed else "FAIL"
            lines.append(
                f"- `{row.model}` `{status}` latency `{row.latency_ms:.1f} ms` "
                f"score `{row.matched_groups}/{row.total_groups}`"
            )
            lines.append(f"  Reply: {row.reply}")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark chat models against the live server.")
    parser.add_argument("--base-url", default="http://192.168.1.105:8000")
    parser.add_argument("--username", default="Admin")
    parser.add_argument("--password", default="password")
    parser.add_argument(
        "--models",
        nargs="+",
        default=["llama3.2:3b", "qwen2.5:3b", "gemma4:e2b"],
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    report_md = args.output_dir / f"model-benchmark-{stamp}.md"
    report_json = args.output_dir / f"model-benchmark-{stamp}.json"

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    _login(session, args.base_url, args.username, args.password)
    documents = _load_documents(session, args.base_url)

    rows: list[ModelCaseResult] = []
    for case in CASES:
        document_id = _find_document_id(documents, case)
        if case.scope_name_contains and not document_id:
            raise BenchmarkFailure(f"Could not find document for case {case.id}.")

        for model in args.models:
            latency_ms, payload = _ask(
                session,
                args.base_url,
                model=model,
                question=case.question,
                document_id=document_id,
            )
            reply = str(payload.get("reply", "")).strip()
            matched_groups, total_groups = _match_groups(reply, case.expected_groups or [])
            rows.append(
                ModelCaseResult(
                    model=model,
                    case_id=case.id,
                    passed=matched_groups == total_groups,
                    latency_ms=latency_ms,
                    reply=reply,
                    matched_groups=matched_groups,
                    total_groups=total_groups,
                    document_id=document_id,
                )
            )

    metadata = {
        "timestamp": stamp,
        "base_url": args.base_url,
        "models": args.models,
        "case_order": [case.id for case in CASES],
        "cases": [asdict(case) for case in CASES],
    }
    payload = {
        "metadata": metadata,
        "results": [asdict(row) for row in rows],
    }
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report_md, metadata, rows)

    print(f"Markdown report: {report_md}")
    print(f"JSON report: {report_json}")

    summary: dict[str, dict[str, float]] = {}
    for model in args.models:
        model_rows = [row for row in rows if row.model == model]
        summary[model] = {
            "passed_cases": sum(1 for row in model_rows if row.passed),
            "total_cases": len(model_rows),
            "avg_latency_ms": round(sum(row.latency_ms for row in model_rows) / len(model_rows), 1),
        }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Benchmark failed: {exc}", file=sys.stderr)
        sys.exit(1)
