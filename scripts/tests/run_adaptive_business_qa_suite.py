from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "temp" / "adaptive-business-qa"


@dataclass
class AdaptiveCase:
    key: str
    question: str
    expected_substrings: list[str]
    expected_source_fragments: list[str]
    forbidden_substrings: list[str] | None = None
    expected_ocr: bool | None = None
    continue_history: bool = False


@dataclass
class AdaptiveResult:
    key: str
    question: str
    ok: bool
    detail: str
    reply: str
    source_names: list[str]
    expected_substrings: list[str]
    expected_source_fragments: list[str]
    retrieval: dict[str, Any] | None


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


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


def _wait_for_health(
    session: requests.Session,
    base_url: str,
    *,
    timeout_seconds: int = 90,
) -> None:
    deadline = time.time() + timeout_seconds
    last_error: str | None = None
    while time.time() < deadline:
        try:
            response = session.get(f"{base_url}/health", timeout=10)
            payload = _ensure_ok(response, "health")
            if payload.get("status") == "ok":
                return
            last_error = f"unexpected health payload: {payload}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(3)
    raise RuntimeError(f"Backend did not become healthy in time: {last_error}")


def _contains_all(haystack: str, needles: list[str]) -> bool:
    lowered = haystack.lower()
    digit_only_haystack = re.sub(r"\D+", "", haystack)
    for needle in needles:
        normalized_needle = needle.lower()
        if normalized_needle in lowered:
            continue
        if needle.isdigit() and needle in digit_only_haystack:
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


def _normalize_text(value: str) -> str:
    return " ".join((value or "").replace("\n", " ").split())


def _preview_text(preview: dict[str, Any]) -> str:
    text = _normalize_text(str(preview.get("extracted_text", "")))
    if text:
        return text
    chunks = preview.get("chunks", [])
    return _normalize_text(" ".join(str(chunk.get("content", "")) for chunk in chunks))


def _fetch_documents(session: requests.Session, base_url: str) -> list[dict[str, Any]]:
    payload = _ensure_ok(
        session.get(
            f"{base_url}/documents",
            params={"limit": 250, "offset": 0},
            timeout=60,
        ),
        "documents",
    )
    return list(payload.get("documents", []))


def _fetch_preview(
    session: requests.Session,
    base_url: str,
    document_id: str,
) -> dict[str, Any]:
    payload = _ensure_ok(
        session.get(f"{base_url}/documents/{document_id}/preview", timeout=60),
        f"preview:{document_id}",
    )
    return dict(payload.get("preview", {}))


def _find_first(
    documents: list[dict[str, Any]],
    previews: dict[str, str],
    *,
    source_kind: str | None = None,
    detected_document_type: str | None = None,
    ocr_used: bool | None = None,
    text_pattern: str | None = None,
) -> dict[str, Any] | None:
    for document in documents:
        if document.get("processing_status") != "processed":
            continue
        if document.get("indexing_status") != "indexed":
            continue
        if source_kind and document.get("source_kind") != source_kind:
            continue
        if detected_document_type and document.get("detected_document_type") != detected_document_type:
            continue
        if ocr_used is not None and bool(document.get("ocr_used")) is not ocr_used:
            continue
        preview_text = previews.get(str(document.get("id")), "")
        if text_pattern and not re.search(text_pattern, preview_text, re.IGNORECASE):
            continue
        return document
    return None


def _derive_summary_anchor(preview_text: str) -> str | None:
    patterns = (
        r"\b(SWIFT)\b",
        r"\b([A-Z]{3,}-\d{2,})\b",
        r"\b(BNP\s+PARIBAS)\b",
        r"\b([A-Z]{2,}\d{0,}[A-Z0-9-]{2,})\b",
        r"\b([A-Za-z]{4,}\s+Policy\s+[A-Za-z0-9-]+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, preview_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    tokens = re.findall(r"[A-Za-z0-9-]{5,}", preview_text)
    return tokens[0] if tokens else None


def _document_group_key(name: str) -> str:
    normalized = str(name or "").lower()
    normalized = re.sub(r"^\d{8}-\d{6}-", "", normalized)
    return normalized


def _find_duplicate_groups(documents: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for document in documents:
        if document.get("processing_status") != "processed":
            continue
        if document.get("indexing_status") != "indexed":
            continue
        group_key = _document_group_key(str(document.get("original_name", "")))
        groups.setdefault(group_key, []).append(document)
    return {
        key: value
        for key, value in groups.items()
        if len(value) >= 2
    }


def _build_cases(
    documents: list[dict[str, Any]],
    previews: dict[str, str],
) -> list[AdaptiveCase]:
    cases: list[AdaptiveCase] = []
    if not documents:
        return cases

    latest_document = documents[0]
    latest_name = str(latest_document.get("original_name", ""))
    if latest_name:
        cases.append(
            AdaptiveCase(
                key="latest_upload",
                question="What is the latest uploaded document?",
                expected_substrings=[latest_name],
                expected_source_fragments=[],
            )
        )
        latest_anchor = _derive_summary_anchor(previews.get(str(latest_document.get("id")), ""))
        if latest_anchor:
            cases.append(
                AdaptiveCase(
                    key="latest_document_summary",
                    question=f"What is {latest_name} about?",
                    expected_substrings=[latest_anchor],
                    expected_source_fragments=[latest_name],
                    forbidden_substrings=["yes."],
                )
            )
            cases.append(
                AdaptiveCase(
                    key="latest_followup_pronoun",
                    question="What is it about?",
                    expected_substrings=[latest_anchor],
                    expected_source_fragments=[latest_name],
                    forbidden_substrings=["yes."],
                    continue_history=True,
                )
            )
        if latest_document.get("document_date"):
            cases.append(
                AdaptiveCase(
                    key="latest_document_date_lookup",
                    question=f"What date is on {latest_name}?",
                    expected_substrings=[str(latest_document["document_date"])[:4]],
                    expected_source_fragments=[latest_name],
                )
            )

    policy_document = _find_first(
        documents,
        previews,
        source_kind="word",
        text_pattern=r"\bpolicy\b",
    )
    if policy_document:
        preview_text = previews[str(policy_document["id"])]
        title_match = re.search(r"^(.*?)(?:\bOwner:|$)", preview_text)
        title = title_match.group(1).strip() if title_match else None
        if title:
            cases.append(
                AdaptiveCase(
                    key="word_document_title",
                    question=f"What title appears in {policy_document['original_name']}?",
                    expected_substrings=[title],
                    expected_source_fragments=[str(policy_document["original_name"])],
                )
            )
        cases.append(
            AdaptiveCase(
                key="policy_inventory",
                question="Do I have any policy documents?",
                expected_substrings=[str(policy_document["original_name"])],
                expected_source_fragments=[],
            )
        )

    duplicate_groups = _find_duplicate_groups(documents)
    policy_group = duplicate_groups.get("policy.docx")
    if policy_group and len(policy_group) >= 2:
        primary = policy_group[0]
        secondary = policy_group[1]
        policy_anchor = _derive_summary_anchor(previews.get(str(primary["id"]), "")) or "Policy"
        cases.append(
            AdaptiveCase(
                key="similar_policy_documents",
                question=f"Which documents are similar to {primary['original_name']}?",
                expected_substrings=["policy.docx"],
                expected_source_fragments=[],
            )
        )
        cases.append(
            AdaptiveCase(
                key="compare_policy_documents",
                question=f"Compare {primary['original_name']} and {secondary['original_name']}.",
                expected_substrings=[policy_anchor],
                expected_source_fragments=[
                    str(primary["original_name"]),
                    str(secondary["original_name"]),
                ],
            )
        )
        cases.append(
            AdaptiveCase(
                key="summarize_policy_documents",
                question="Summarize the policy documents.",
                expected_substrings=[policy_anchor],
                expected_source_fragments=["policy.docx"],
            )
        )

    spreadsheet_document = _find_first(
        documents,
        previews,
        source_kind="spreadsheet",
        text_pattern=r"\bQ2\b.*?\bTotal\b[: ]+\d+",
    )
    if spreadsheet_document:
        preview_text = previews[str(spreadsheet_document["id"])]
        total_match = re.search(r"\bQ2\b.*?\bTotal\b[: ]+(\d+)", preview_text, re.IGNORECASE)
        if total_match:
            cases.append(
                AdaptiveCase(
                    key="spreadsheet_metric_lookup",
                    question=f"What is the Q2 total value in {spreadsheet_document['original_name']}?",
                    expected_substrings=[total_match.group(1)],
                    expected_source_fragments=[str(spreadsheet_document["original_name"])],
                )
            )

    config_document = _find_first(
        documents,
        previews,
        source_kind="config",
        text_pattern=r"<port>\d+</port>|port[:> ]+\d+",
    )
    if config_document:
        preview_text = previews[str(config_document["id"])]
        port_match = re.search(r"<port>(\d+)</port>|port[:> ]+(\d+)", preview_text, re.IGNORECASE)
        port = next((group for group in port_match.groups() if group), None) if port_match else None
        if port:
            cases.append(
                AdaptiveCase(
                    key="config_port_lookup",
                    question=f"What service port is configured in {config_document['original_name']}?",
                    expected_substrings=[port],
                    expected_source_fragments=[str(config_document["original_name"])],
                )
            )

    json_document = _find_first(
        documents,
        previews,
        source_kind="json",
        text_pattern=r"support_owner",
    )
    if json_document:
        preview_text = previews[str(json_document["id"])]
        owner_match = re.search(r'"support_owner"\s*:\s*"([^"]+)"', preview_text)
        if owner_match:
            cases.append(
                AdaptiveCase(
                    key="json_owner_lookup",
                    question=f"What is the support owner in {json_document['original_name']}?",
                    expected_substrings=[owner_match.group(1)],
                    expected_source_fragments=[str(json_document["original_name"])],
                )
            )

    text_document = _find_first(
        documents,
        previews,
        source_kind="text",
        text_pattern=r"codename[: ]+[A-Z0-9-]+",
    )
    if text_document:
        preview_text = previews[str(text_document["id"])]
        code_match = re.search(r"codename[: ]+([A-Z0-9-]+)", preview_text, re.IGNORECASE)
        if code_match:
            cases.append(
                AdaptiveCase(
                    key="text_codename_lookup",
                    question=f"What project codename is mentioned in {text_document['original_name']}?",
                    expected_substrings=[code_match.group(1)],
                    expected_source_fragments=[str(text_document["original_name"])],
                )
            )

    markdown_document = _find_first(
        documents,
        previews,
        source_kind="markdown",
        text_pattern=r"region[: ]+[A-Za-z0-9-]+",
    )
    if markdown_document:
        preview_text = previews[str(markdown_document["id"])]
        region_match = re.search(r"region[: ]+([A-Za-z0-9-]+)", preview_text, re.IGNORECASE)
        if region_match:
            cases.append(
                AdaptiveCase(
                    key="markdown_region_lookup",
                    question=f"Which deployment region is mentioned in {markdown_document['original_name']}?",
                    expected_substrings=[region_match.group(1)],
                    expected_source_fragments=[str(markdown_document["original_name"])],
                )
            )

    presentation_document = _find_first(
        documents,
        previews,
        source_kind="presentation",
        text_pattern=r"Milestone[: ]+[A-Za-z0-9 -]+",
    )
    if presentation_document:
        preview_text = previews[str(presentation_document["id"])]
        milestone_match = re.search(
            r"Milestone[: ]+([A-Za-z0-9 -]+?)(?:Owner[: ]|$)",
            preview_text,
            re.IGNORECASE,
        )
        if milestone_match:
            cases.append(
                AdaptiveCase(
                    key="presentation_milestone_lookup",
                    question=f"What milestone name appears in {presentation_document['original_name']}?",
                    expected_substrings=[milestone_match.group(1).strip()],
                    expected_source_fragments=[str(presentation_document["original_name"])],
                )
            )

    csv_document = _find_first(
        documents,
        previews,
        source_kind="csv",
        text_pattern=r"INV-\d+.*?\d{3,}",
    )
    if csv_document:
        preview_text = previews[str(csv_document["id"])]
        invoice_match = re.search(r"(INV-\d+)\s*\|\s*(\d+)", preview_text, re.IGNORECASE)
        if invoice_match:
            cases.append(
                AdaptiveCase(
                    key="csv_invoice_lookup",
                    question=f"What amount is listed for {invoice_match.group(1)} in {csv_document['original_name']}?",
                    expected_substrings=[invoice_match.group(2)],
                    expected_source_fragments=[str(csv_document["original_name"])],
                )
            )

    dated_invoice_document = _find_first(
        documents,
        previews,
        detected_document_type="invoice",
    )
    if dated_invoice_document and dated_invoice_document.get("document_date"):
        year = str(dated_invoice_document["document_date"])[:4]
        cases.append(
            AdaptiveCase(
                key="invoice_year_inventory",
                question=f"Which invoices do I have from {year}?",
                expected_substrings=[str(dated_invoice_document["original_name"])],
                expected_source_fragments=[],
            )
        )

    code_document = _find_first(
        documents,
        previews,
        source_kind="code",
        text_pattern=r"def\s+[A-Za-z_][A-Za-z0-9_]*",
    )
    if code_document:
        preview_text = previews[str(code_document["id"])]
        function_match = re.search(r"def\s+([A-Za-z_][A-Za-z0-9_]*)", preview_text)
        if function_match:
            cases.append(
                AdaptiveCase(
                    key="code_function_lookup",
                    question=f"What function name appears in {code_document['original_name']}?",
                    expected_substrings=[function_match.group(1)],
                    expected_source_fragments=[str(code_document["original_name"])],
                )
            )

    scanned_pdf = _find_first(
        documents,
        previews,
        source_kind="pdf",
        ocr_used=True,
        text_pattern=r"\b[A-Z]{2,}-\d{2,}\b",
    )
    if scanned_pdf:
        preview_text = previews[str(scanned_pdf["id"])]
        code_match = re.search(r"\b([A-Z]{2,}-\d{2,})\b", preview_text)
        if code_match:
            cases.append(
                AdaptiveCase(
                    key="ocr_pdf_code_lookup",
                    question=f"What code appears in the scanned PDF {scanned_pdf['original_name']}?",
                    expected_substrings=[code_match.group(1)],
                    expected_source_fragments=[str(scanned_pdf["original_name"])],
                    expected_ocr=True,
                )
            )

    scanned_image = _find_first(
        documents,
        previews,
        source_kind="image",
        ocr_used=True,
        text_pattern=r"\b[A-Z]{2,}-\d{2,}\b",
    )
    if scanned_image:
        preview_text = previews[str(scanned_image["id"])]
        code_match = re.search(r"\b([A-Z]{2,}-\d{2,})\b", preview_text)
        if code_match:
            cases.append(
                AdaptiveCase(
                    key="ocr_image_code_lookup",
                    question=f"What code appears in the scanned image {scanned_image['original_name']}?",
                    expected_substrings=[code_match.group(1)],
                    expected_source_fragments=[str(scanned_image["original_name"])],
                    expected_ocr=True,
                )
            )

    if markdown_document and 'region_match' in locals() and region_match:
        cases.append(
            AdaptiveCase(
                key="mention_lookup_markdown",
                question=f"Which document mentions {region_match.group(1)}?",
                expected_substrings=[region_match.group(1)],
                expected_source_fragments=[str(markdown_document["original_name"])],
            )
        )
        cases.append(
            AdaptiveCase(
                key="relevance_lookup_markdown",
                question=f"Which document is most relevant for {region_match.group(1)}?",
                expected_substrings=[region_match.group(1)],
                expected_source_fragments=[str(markdown_document["original_name"])],
            )
        )
        cases.append(
            AdaptiveCase(
                key="best_support_markdown",
                question=(
                    "Which documents best support the statement that the primary "
                    f"deployment region is {region_match.group(1)}?"
                ),
                expected_substrings=[region_match.group(1)],
                expected_source_fragments=["guide.md"],
            )
        )

    if policy_document:
        compliance_match = re.search(
            r"Owner:\s*([A-Za-z][A-Za-z ]+?)(?:\s+Purpose:|$)",
            previews[str(policy_document["id"])],
        )
        if compliance_match:
            cases.append(
                AdaptiveCase(
                    key="topic_presence_policy",
                    question=f"Does {policy_document['original_name']} mention {compliance_match.group(1).strip()}?",
                    expected_substrings=[compliance_match.group(1).strip()],
                    expected_source_fragments=[str(policy_document["original_name"])],
                )
            )

    csv_group = duplicate_groups.get("finance.csv")
    if csv_group and len(csv_group) >= 2:
        primary = csv_group[0]
        secondary = csv_group[1]
        cases.append(
            AdaptiveCase(
                key="overlap_finance_documents",
                question=f"Which documents overlap with {primary['original_name']}?",
                expected_substrings=["finance.csv"],
                expected_source_fragments=[],
            )
        )

    roadmap_group = duplicate_groups.get("roadmap.pptx")
    if roadmap_group:
        roadmap_anchor = (
            milestone_match.group(1).strip()
            if 'milestone_match' in locals() and milestone_match
            else _derive_summary_anchor(previews.get(str(roadmap_group[0]["id"]), "")) or "Roadmap"
        )
        cases.append(
            AdaptiveCase(
                key="summarize_roadmap_documents",
                question="Summarize the roadmap presentations.",
                expected_substrings=[roadmap_anchor],
                expected_source_fragments=["roadmap.pptx"],
            )
        )

    metrics_group = duplicate_groups.get("metrics.xlsx")
    if metrics_group and spreadsheet_document:
        q2_total = total_match.group(1) if 'total_match' in locals() and total_match else None
        if q2_total:
            cases.append(
                AdaptiveCase(
                    key="spreadsheet_disagreement_check",
                    question="Do any of the spreadsheet documents disagree about the Q2 total?",
                    expected_substrings=[q2_total],
                    expected_source_fragments=[],
                )
            )

    return cases


def _run_case(
    session: requests.Session,
    base_url: str,
    model: str,
    case: AdaptiveCase,
    history: list[dict[str, Any]],
) -> tuple[AdaptiveResult, list[dict[str, Any]]]:
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
    forbidden_ok = not any(
        forbidden.lower() in reply.lower()
        for forbidden in (case.forbidden_substrings or [])
    )
    ocr_ok = True
    if case.expected_ocr is not None:
        ocr_ok = bool(sources) and all(
            bool(source.get("ocr_used")) is case.expected_ocr for source in sources
        )

    ok = substring_ok and source_ok and forbidden_ok and ocr_ok
    detail = ", ".join(
        [
            "reply-match" if substring_ok else "reply-mismatch",
            "source-match" if source_ok else "source-mismatch",
            "style-match" if forbidden_ok else "style-mismatch",
            (
                "ocr-match"
                if case.expected_ocr is None or ocr_ok
                else "ocr-mismatch"
            ),
        ]
    )

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

    return (
        AdaptiveResult(
            key=case.key,
            question=case.question,
            ok=ok,
            detail=detail,
            reply=reply,
            source_names=source_names,
            expected_substrings=case.expected_substrings,
            expected_source_fragments=case.expected_source_fragments,
            retrieval=payload.get("retrieval"),
        ),
        updated_history,
    )


def _write_markdown(path: Path, metadata: dict[str, Any], results: list[AdaptiveResult]) -> None:
    passed = sum(1 for result in results if result.ok)
    lines = [
        "# Adaptive Business QA Report",
        "",
        f"- Timestamp: {metadata['timestamp']}",
        f"- Base URL: {metadata['base_url']}",
        f"- Model: {metadata['model']}",
        f"- Generated cases: {metadata['generated_cases']}",
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
        lines.append(
            f"  Expected: {', '.join(result.expected_substrings) if result.expected_substrings else 'none'}"
        )
        lines.append(
            f"  Sources: {', '.join(result.source_names) if result.source_names else 'none'}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run adaptive enterprise-style document QA checks against Local AI OS."
    )
    parser.add_argument("--base-url", default="http://192.168.1.105:8000")
    parser.add_argument("--username", default="Admin")
    parser.add_argument("--password", default="password")
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    report_md = args.output_dir / f"adaptive-business-qa-{stamp}.md"
    report_json = args.output_dir / f"adaptive-business-qa-{stamp}.json"

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    _wait_for_health(session, args.base_url)
    _login(session, args.base_url, args.username, args.password)

    documents = _fetch_documents(session, args.base_url)
    previews = {
        str(document["id"]): _preview_text(_fetch_preview(session, args.base_url, str(document["id"])))
        for document in documents
    }
    cases = _build_cases(documents, previews)
    if len(cases) < 8:
        raise RuntimeError(
            f"Adaptive suite could only generate {len(cases)} cases; expected at least 8."
        )

    results: list[AdaptiveResult] = []
    history: list[dict[str, Any]] = []
    for case in cases:
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
        "generated_cases": len(cases),
        "passed": sum(1 for result in results if result.ok),
        "total": len(results),
    }
    report_json.write_text(
        json.dumps(
            {
                "metadata": metadata,
                "cases": [asdict(case) for case in cases],
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
