from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_DIR = ROOT / "backend" / "evals" / "fixtures" / "synthetic"
DEFAULT_OUTPUT_DIR = ROOT / "temp" / "enterprise-document-intelligence"


@dataclass
class UploadedFixture:
    key: str
    path: Path
    document_id: str
    document_name: str


@dataclass
class IntelligenceCase:
    key: str
    question: str
    expected_substrings: list[str]
    expected_source_fragments: list[str]


@dataclass
class IntelligenceResult:
    key: str
    question: str
    ok: bool
    detail: str
    reply: str
    source_names: list[str]
    expected_substrings: list[str]
    expected_source_fragments: list[str]
    retrieval: dict[str, Any] | None


FIXTURE_FILES = {
    "contract": "Northstar_Aerotech_Master_Service_Agreement_2026-01-15.txt",
    "incident": "Meridian_Food_Service_Incident_Report_2025-11-03.txt",
    "quote": "Aurora_Cycling_Quote_2026-04-22.txt",
    "policy": "Solstice_Logistics_Travel_Policy_2025-08-01.txt",
    "invoice": "BlueHarbor_Medical_Invoice_2026-02-14.txt",
    "code": "Fjordbyte_SharePoint_Sync_Service.ts",
    "runbook": "BlueHarbor_SharePoint_Knowledge_Runbook.docx",
    "briefing": "Solstice_SharePoint_Rollout_Briefing.pptx",
}


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _ensure_ok(response: requests.Response, context: str) -> dict[str, Any]:
    if not response.ok:
        raise RuntimeError(f"{context} failed: {response.status_code} {response.text[:500]}")
    if not response.content:
        return {}
    return response.json()


def _wait_for_health(session: requests.Session, base_url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    last_error: str | None = None
    while time.time() < deadline:
        try:
            payload = _ensure_ok(session.get(f"{base_url}/health", timeout=10), "health")
            if payload.get("status") == "ok":
                return
            last_error = str(payload)
        except Exception as exc:
            last_error = str(exc)
        time.sleep(3)
    raise RuntimeError(f"Backend did not become healthy in time: {last_error}")


def _login(session: requests.Session, base_url: str, username: str, password: str) -> None:
    _ensure_ok(
        session.post(
            f"{base_url}/auth/login",
            json={"username": username, "password": password},
            timeout=30,
        ),
        "login",
    )


def _upload_document(session: requests.Session, base_url: str, path: Path) -> dict[str, Any]:
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as handle:
        response = session.post(
            f"{base_url}/documents/upload",
            files={"file": (path.name, handle, content_type)},
            timeout=180,
        )
    return dict(_ensure_ok(response, f"upload:{path.name}")["document"])


def _wait_for_document(
    session: requests.Session,
    base_url: str,
    document_id: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_document: dict[str, Any] = {}
    while time.time() < deadline:
        payload = _ensure_ok(
            session.get(f"{base_url}/documents", params={"limit": 250}, timeout=60),
            "documents",
        )
        for document in payload.get("documents", []):
            if document.get("id") != document_id:
                continue
            last_document = dict(document)
            if (
                document.get("processing_status") == "processed"
                and document.get("indexing_status") == "indexed"
            ):
                return last_document
        time.sleep(4)
    raise RuntimeError(f"Document {document_id} did not finish processing: {last_document}")


def _contains_all(haystack: str, needles: list[str]) -> bool:
    lowered = haystack.lower()
    compact = "".join(character for character in lowered if character.isalnum())
    for needle in needles:
        lowered_needle = needle.lower()
        if lowered_needle in lowered:
            continue
        compact_needle = "".join(character for character in lowered_needle if character.isalnum())
        if compact_needle and compact_needle in compact:
            continue
        return False
    return True


def _source_match(source_names: list[str], fragments: list[str]) -> bool:
    if not fragments:
        return True
    lowered_sources = [name.lower() for name in source_names]
    return all(
        any(fragment.lower() in source_name for source_name in lowered_sources)
        for fragment in fragments
    )


def _build_cases(uploaded: dict[str, UploadedFixture]) -> list[IntelligenceCase]:
    contract = uploaded["contract"].document_name
    incident = uploaded["incident"].document_name
    quote = uploaded["quote"].document_name
    policy = uploaded["policy"].document_name
    invoice = uploaded["invoice"].document_name
    code = uploaded["code"].document_name

    return [
        IntelligenceCase(
            key="contract_summary",
            question=f"What is {contract} about?",
            expected_substrings=["Project Nebula Arc"],
            expected_source_fragments=[contract],
        ),
        IntelligenceCase(
            key="contract_deadlines",
            question=f"What deadlines are in {contract}?",
            expected_substrings=["60 days", "30 days"],
            expected_source_fragments=[contract],
        ),
        IntelligenceCase(
            key="incident_risks",
            question=f"What risks or issues are in {incident}?",
            expected_substrings=["threshold", "quarantined"],
            expected_source_fragments=[incident],
        ),
        IntelligenceCase(
            key="incident_actions",
            question=f"What action items are in {incident}?",
            expected_substrings=["Replace", "seven days"],
            expected_source_fragments=[incident],
        ),
        IntelligenceCase(
            key="quote_deadlines",
            question=f"What deadlines are in {quote}?",
            expected_substrings=["2026-05-15", "21 days"],
            expected_source_fragments=[quote],
        ),
        IntelligenceCase(
            key="policy_deadlines",
            question=f"What deadlines are in {policy}?",
            expected_substrings=["14 days"],
            expected_source_fragments=[policy],
        ),
        IntelligenceCase(
            key="invoice_due_date",
            question=f"What is the due date in {invoice}?",
            expected_substrings=["2026-03-15"],
            expected_source_fragments=[invoice],
        ),
        IntelligenceCase(
            key="code_function",
            question=f"What does the SharePoint sync service in {code} do?",
            expected_substrings=["SharePoint", "knowledge"],
            expected_source_fragments=[code],
        ),
    ]


def _run_case(
    session: requests.Session,
    base_url: str,
    model: str,
    case: IntelligenceCase,
) -> IntelligenceResult:
    payload = _ensure_ok(
        session.post(
            f"{base_url}/chat",
            json={
                "message": case.question,
                "model": model,
                "history": [],
                "document_ids": [],
                "persist_conversation": False,
            },
            timeout=240,
        ),
        f"chat:{case.key}",
    )
    reply = str(payload.get("reply", ""))
    sources = payload.get("sources", [])
    source_names = [
        str(source.get("document_name", ""))
        for source in sources
        if source.get("document_name")
    ]
    reply_ok = _contains_all(reply, case.expected_substrings)
    sources_ok = _source_match(source_names, case.expected_source_fragments)
    ok = reply_ok and sources_ok
    return IntelligenceResult(
        key=case.key,
        question=case.question,
        ok=ok,
        detail=", ".join(
            [
                "reply-match" if reply_ok else "reply-mismatch",
                "source-match" if sources_ok else "source-mismatch",
            ]
        ),
        reply=reply,
        source_names=source_names,
        expected_substrings=case.expected_substrings,
        expected_source_fragments=case.expected_source_fragments,
        retrieval=payload.get("retrieval"),
    )


def _write_report(
    path: Path,
    metadata: dict[str, Any],
    uploaded: dict[str, UploadedFixture],
    results: list[IntelligenceResult],
) -> None:
    passed = sum(1 for result in results if result.ok)
    lines = [
        "# Enterprise Document Intelligence Report",
        "",
        f"- Timestamp: {metadata['timestamp']}",
        f"- Base URL: {metadata['base_url']}",
        f"- Model: {metadata['model']}",
        f"- Uploaded fixtures: {len(uploaded)}",
        f"- Passed: {passed}/{len(results)}",
        "",
        "## Uploaded",
        "",
    ]
    for fixture in uploaded.values():
        lines.append(f"- `{fixture.key}`: {fixture.document_name}")

    lines.extend(["", "## Results", ""])
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        lines.append(f"- `{status}` {result.key}: {result.detail}")
        lines.append(f"  Question: {result.question}")
        lines.append(f"  Reply: {result.reply}")
        lines.append(
            f"  Expected: {', '.join(result.expected_substrings) if result.expected_substrings else 'none'}"
        )
        lines.append(
            f"  Sources: {', '.join(result.source_names) if result.source_names else 'none'}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Upload enterprise fixtures and test document intelligence answers."
    )
    parser.add_argument("--base-url", default="http://192.168.1.105:8000")
    parser.add_argument("--username", default="Admin")
    parser.add_argument("--password", default="password")
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--fixture-dir", type=Path, default=DEFAULT_FIXTURE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--health-timeout", type=int, default=120)
    parser.add_argument("--process-timeout", type=int, default=240)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    report_md = args.output_dir / f"enterprise-document-intelligence-{stamp}.md"
    report_json = args.output_dir / f"enterprise-document-intelligence-{stamp}.json"

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    _wait_for_health(session, args.base_url, args.health_timeout)
    _login(session, args.base_url, args.username, args.password)

    uploaded: dict[str, UploadedFixture] = {}
    for key, relative_name in FIXTURE_FILES.items():
        path = args.fixture_dir / relative_name
        if not path.exists():
            raise RuntimeError(f"Fixture missing: {path}")
        document = _upload_document(session, args.base_url, path)
        processed = _wait_for_document(
            session,
            args.base_url,
            str(document["id"]),
            args.process_timeout,
        )
        uploaded[key] = UploadedFixture(
            key=key,
            path=path,
            document_id=str(processed["id"]),
            document_name=str(processed["original_name"]),
        )
        print(f"[UPLOAD] {key}: {processed['original_name']}")

    cases = _build_cases(uploaded)
    results = [
        _run_case(session=session, base_url=args.base_url, model=args.model, case=case)
        for case in cases
    ]
    for result in results:
        print(f"[{'PASS' if result.ok else 'FAIL'}] {result.key}: {result.detail}")

    metadata = {
        "timestamp": stamp,
        "base_url": args.base_url,
        "model": args.model,
        "passed": sum(1 for result in results if result.ok),
        "total": len(results),
    }
    report_json.write_text(
        json.dumps(
            {
                "metadata": metadata,
                "uploaded": [asdict(item) for item in uploaded.values()],
                "results": [asdict(result) for result in results],
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    _write_report(report_md, metadata, uploaded, results)
    print(f"Markdown report: {report_md}")
    print(f"JSON report: {report_json}")

    return 0 if metadata["passed"] == metadata["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
