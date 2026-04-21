from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "temp" / "business-document-qa"


@dataclass
class BusinessQuestion:
    key: str
    question: str
    expected_substrings: list[str]
    expected_source_fragments: list[str]
    expected_ocr: bool | None = None
    continue_history: bool = False


@dataclass
class BusinessQuestionResult:
    key: str
    question: str
    ok: bool
    detail: str
    reply: str
    source_names: list[str]
    expected_substrings: list[str]
    expected_source_fragments: list[str]
    retrieval: dict[str, Any] | None


TEST_CASES: list[BusinessQuestion] = [
    BusinessQuestion(
        key="latest_upload",
        question="What is the latest uploaded document?",
        expected_substrings=["FS 130_04_2026_nV68.pdf"],
        expected_source_fragments=[],
    ),
    BusinessQuestion(
        key="latest_upload_followup",
        question="What is FS about?",
        expected_substrings=["SWIFT"],
        expected_source_fragments=["FS 130_04_2026_nV68.pdf"],
        continue_history=True,
    ),
    BusinessQuestion(
        key="policy_title",
        question="What policy title appears in the policy document?",
        expected_substrings=["Retention Policy Aurora"],
        expected_source_fragments=["policy.docx"],
    ),
    BusinessQuestion(
        key="spreadsheet_q2",
        question="What is the Q2 total value in the spreadsheet?",
        expected_substrings=["982"],
        expected_source_fragments=["metrics.xlsx"],
    ),
    BusinessQuestion(
        key="xml_port",
        question="What service port is configured in the XML file?",
        expected_substrings=["4317"],
        expected_source_fragments=["service.xml"],
    ),
    BusinessQuestion(
        key="json_owner",
        question="What support owner value is in the JSON profile?",
        expected_substrings=["Marta Linden"],
        expected_source_fragments=["profile.json"],
    ),
    BusinessQuestion(
        key="notes_codename",
        question="What project codename is in the notes file?",
        expected_substrings=["NEBULA-FOX"],
        expected_source_fragments=["notes.txt"],
    ),
    BusinessQuestion(
        key="roadmap_milestone",
        question="What milestone name appears in the roadmap presentation?",
        expected_substrings=["Orion Launch"],
        expected_source_fragments=["roadmap.pptx"],
    ),
    BusinessQuestion(
        key="invoice_amount",
        question="What invoice amount is listed for INV-77?",
        expected_substrings=["18450"],
        expected_source_fragments=["finance.csv"],
    ),
    BusinessQuestion(
        key="scanned_pdf_incident",
        question="What incident code appears in the scanned PDF?",
        expected_substrings=["INC-2048"],
        expected_source_fragments=["scan-pdf.pdf"],
        expected_ocr=True,
    ),
    BusinessQuestion(
        key="scanned_image_access_code",
        question="What access code appears in the scanned image?",
        expected_substrings=["AURORA-17"],
        expected_source_fragments=["scan-image.png"],
        expected_ocr=True,
    ),
    BusinessQuestion(
        key="worker_function",
        question="What function returns the audit status?",
        expected_substrings=["build_audit_status"],
        expected_source_fragments=["worker.py"],
    ),
]


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _contains_all(haystack: str, needles: list[str]) -> bool:
    lowered = haystack.lower()
    return all(needle.lower() in lowered for needle in needles)


def _source_match(source_names: list[str], fragments: list[str]) -> bool:
    if not fragments:
        return True
    lowered_sources = [name.lower() for name in source_names]
    return all(
        any(fragment.lower() in source_name for source_name in lowered_sources)
        for fragment in fragments
    )


def _ensure_ok(response: requests.Response, context: str) -> dict[str, Any]:
    if not response.ok:
        raise RuntimeError(f"{context} failed: {response.status_code} {response.text[:400]}")
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


def _run_case(
    session: requests.Session,
    base_url: str,
    model: str,
    case: BusinessQuestion,
    history: list[dict[str, Any]],
) -> tuple[BusinessQuestionResult, list[dict[str, Any]]]:
    response = session.post(
        f"{base_url}/chat",
        json={
            "message": case.question,
            "model": model,
            "history": history,
            "document_ids": [],
            "persist_conversation": False,
        },
        timeout=180,
    )
    payload = _ensure_ok(response, f"chat:{case.key}")
    reply = str(payload.get("reply", ""))
    sources = payload.get("sources", [])
    source_names = [
        str(source.get("document_name", ""))
        for source in sources
        if source.get("document_name")
    ]

    substring_ok = _contains_all(reply, case.expected_substrings)
    source_ok = _source_match(source_names, case.expected_source_fragments)
    ocr_ok = True
    if case.expected_ocr is not None:
        ocr_ok = bool(sources) and all(
            bool(source.get("ocr_used")) is case.expected_ocr for source in sources
        )

    ok = substring_ok and source_ok and ocr_ok
    detail_parts: list[str] = []
    detail_parts.append("reply-match" if substring_ok else "reply-mismatch")
    detail_parts.append("source-match" if source_ok else "source-mismatch")
    if case.expected_ocr is not None:
        detail_parts.append("ocr-match" if ocr_ok else "ocr-mismatch")

    updated_history = history + [
        {"role": "user", "content": case.question},
        {
            "role": "assistant",
            "content": reply,
            "model": payload.get("model"),
            "sources": sources,
            "retrieval": payload.get("retrieval"),
        },
    ]

    result = BusinessQuestionResult(
        key=case.key,
        question=case.question,
        ok=ok,
        detail=", ".join(detail_parts),
        reply=reply,
        source_names=source_names,
        expected_substrings=case.expected_substrings,
        expected_source_fragments=case.expected_source_fragments,
        retrieval=payload.get("retrieval"),
    )
    return result, updated_history


def _write_markdown(path: Path, metadata: dict[str, Any], results: list[BusinessQuestionResult]) -> None:
    passed = sum(1 for result in results if result.ok)
    lines = [
        "# Business Document QA Report",
        "",
        f"- Timestamp: {metadata['timestamp']}",
        f"- Base URL: {metadata['base_url']}",
        f"- Model: {metadata['model']}",
        f"- Passed: {passed}/{len(results)}",
        "",
        "## Results",
        "",
    ]

    for result in results:
        status = "PASS" if result.ok else "FAIL"
        lines.append(f"- `{status}` {result.key}: {result.detail}")
        lines.append(f"  Question: {result.question}")
        lines.append(f"  Reply: {result.reply}")
        if result.source_names:
            lines.append(f"  Sources: {', '.join(result.source_names)}")
        else:
            lines.append("  Sources: none")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run enterprise-style document QA checks against Local AI OS.")
    parser.add_argument("--base-url", default="http://192.168.1.105:8000")
    parser.add_argument("--username", default="Admin")
    parser.add_argument("--password", default="password")
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    report_md = args.output_dir / f"business-document-qa-{stamp}.md"
    report_json = args.output_dir / f"business-document-qa-{stamp}.json"

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    _ensure_ok(session.get(f"{args.base_url}/health", timeout=30), "health")
    _login(session, args.base_url, args.username, args.password)

    results: list[BusinessQuestionResult] = []
    history: list[dict[str, Any]] = []
    for case in TEST_CASES:
        if not case.continue_history:
            history = []
        result, history = _run_case(
            session=session,
            base_url=args.base_url,
            model=args.model,
            case=case,
            history=history,
        )
        results.append(result)
        print(f"[{'PASS' if result.ok else 'FAIL'}] {case.key}: {result.detail}")

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
                "results": [asdict(result) for result in results],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_markdown(report_md, metadata, results)

    print(f"Markdown report: {report_md}")
    print(f"JSON report: {report_json}")

    if metadata["passed"] != metadata["total"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
