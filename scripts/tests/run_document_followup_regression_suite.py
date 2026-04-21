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
DEFAULT_OUTPUT_DIR = ROOT / "temp" / "document-followup-regression"


@dataclass
class RegressionResult:
    key: str
    question: str
    ok: bool
    detail: str
    reply: str
    source_names: list[str]
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


def _wait_for_login_ready(
    session: requests.Session,
    base_url: str,
    username: str,
    password: str,
    *,
    timeout_seconds: int = 120,
) -> None:
    deadline = time.time() + timeout_seconds
    last_error: str | None = None
    while time.time() < deadline:
        try:
            _login(session, base_url, username, password)
            return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(3)
    raise RuntimeError(f"Login did not become ready in time: {last_error}")


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


def _fetch_preview_text(
    session: requests.Session,
    base_url: str,
    document_id: str,
) -> str:
    payload = _ensure_ok(
        session.get(f"{base_url}/documents/{document_id}/preview", timeout=60),
        f"preview:{document_id}",
    )
    preview = payload.get("preview", {})
    text = str(preview.get("extracted_text", ""))
    if text.strip():
        return " ".join(text.split())
    chunks = preview.get("chunks", [])
    return " ".join(
        " ".join(str(chunk.get("content", "")).split())
        for chunk in chunks
    ).strip()


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
        groups.setdefault(_document_group_key(str(document.get("original_name", ""))), []).append(document)
    return {key: value for key, value in groups.items() if len(value) >= 2}


def _extract_companies(text: str) -> list[str]:
    candidates: list[str] = []
    patterns = (
        r"\b([A-Z][A-Za-z&.\-]+(?:\s+[A-Z][A-Za-z&.\-]+){1,5}\s+(?:AB|LLC|Ltd|GmbH|S\.A\.|SA))\b",
        r"\b([A-Z][A-Za-z&.\-]+(?:\s+[A-Z][A-Za-z&.\-]+){1,5})\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            candidate = match.group(1).strip(" ,.;:")
            if len(candidate.split()) >= 2 and candidate not in candidates:
                candidates.append(candidate)
    return candidates[:4]


def _extract_products(text: str) -> list[str]:
    candidates: list[str] = []
    patterns = (
        r"(?i)(?:product|item|description)\s*[:\-]\s*([A-Za-z][A-Za-z0-9 /(),-]{2,80})",
        r"(?i)barcode\s+([A-Za-z][A-Za-z0-9 /(),-]{2,60})\s+(?:quantity|qty|ilość|ilosc)\b",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            candidate = match.group(1).strip(" ,.;:")
            if candidate and candidate not in candidates:
                candidates.append(candidate)

    if not candidates and "bicycle part" in text.lower():
        candidates.append("Bicycle part")

    return candidates[:4]


def _pick_invoice_document(
    documents: list[dict[str, Any]],
    previews: dict[str, str],
) -> dict[str, Any] | None:
    for document in documents:
        if document.get("detected_document_type") != "invoice":
            continue
        if _extract_products(previews.get(str(document.get("id")), "")):
            return document
    for document in documents:
        if document.get("detected_document_type") == "invoice":
            return document
    return None


def _run_case(
    session: requests.Session,
    base_url: str,
    model: str,
    question: str,
    history: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    response = session.post(
        f"{base_url}/chat",
        json={
            "message": question,
            "model": model,
            "history": history,
            "document_ids": [],
            "persist_conversation": False,
        },
        timeout=180,
    )
    payload = _ensure_ok(response, f"chat:{question}")
    updated_history = history + [
        {"role": "user", "content": question},
        {
            "role": "assistant",
            "content": payload.get("reply", ""),
            "model": payload.get("model"),
            "sources": payload.get("sources", []),
            "retrieval": payload.get("retrieval"),
        },
    ]
    return payload, updated_history


def _has_duplicate_pair(reply: str, duplicate_groups: dict[str, list[dict[str, Any]]]) -> bool:
    lowered = reply.lower()
    for group in duplicate_groups.values():
        names = [str(item.get("original_name", "")).lower() for item in group[:3]]
        hit_count = sum(name in lowered for name in names if name)
        if hit_count >= 2:
            return True
    return False


def _result(
    *,
    key: str,
    question: str,
    payload: dict[str, Any],
    ok: bool,
    detail: str,
) -> RegressionResult:
    return RegressionResult(
        key=key,
        question=question,
        ok=ok,
        detail=detail,
        reply=str(payload.get("reply", "")),
        source_names=[
            str(source.get("document_name", ""))
            for source in payload.get("sources", [])
            if source.get("document_name")
        ],
        retrieval=payload.get("retrieval"),
    )


def _write_report(path: Path, metadata: dict[str, Any], results: list[RegressionResult]) -> None:
    passed = sum(1 for result in results if result.ok)
    lines = [
        "# Document Follow-up Regression Report",
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
        lines.append(
            f"  Sources: {', '.join(result.source_names) if result.source_names else 'none'}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run regression checks for document follow-up conversations.")
    parser.add_argument("--base-url", default="http://192.168.1.105:8000")
    parser.add_argument("--username", default="Admin")
    parser.add_argument("--password", default="password")
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    report_md = args.output_dir / f"followup-regression-{stamp}.md"
    report_json = args.output_dir / f"followup-regression-{stamp}.json"

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    _wait_for_login_ready(session, args.base_url, args.username, args.password)

    documents = _fetch_documents(session, args.base_url)
    if not documents:
        raise RuntimeError("No documents available for regression checks.")

    previews = {
        str(document["id"]): _fetch_preview_text(session, args.base_url, str(document["id"]))
        for document in documents
    }
    duplicate_groups = _find_duplicate_groups(documents)
    if not duplicate_groups:
        raise RuntimeError("Could not find duplicate document groups for similarity regression.")

    latest_document = documents[0]
    largest_document = max(documents, key=lambda item: int(item.get("size_bytes", 0)))
    invoice_document = _pick_invoice_document(documents, previews)
    if invoice_document is None:
        raise RuntimeError("Could not find a suitable invoice document for follow-up regression.")

    invoice_preview = previews[str(invoice_document["id"])]
    invoice_companies = _extract_companies(invoice_preview)
    invoice_products = _extract_products(invoice_preview)

    results: list[RegressionResult] = []
    history: list[dict[str, Any]] = []

    payload, history = _run_case(
        session,
        args.base_url,
        args.model,
        "Can you find some documents that are very simular?",
        history,
    )
    ok = _has_duplicate_pair(str(payload.get("reply", "")), duplicate_groups)
    results.append(
        _result(
            key="similarity_general",
            question="Can you find some documents that are very simular?",
            payload=payload,
            ok=ok,
            detail="found-duplicate-pair" if ok else "missing-duplicate-pair",
        )
    )

    payload, history = _run_case(
        session,
        args.base_url,
        args.model,
        "Is that the only document that is simular?",
        history,
    )
    reply = str(payload.get("reply", "")).lower()
    ok = "other similar pairs include" in reply or "not the only" in reply or _has_duplicate_pair(reply, duplicate_groups)
    results.append(
        _result(
            key="similarity_followup",
            question="Is that the only document that is simular?",
            payload=payload,
            ok=ok,
            detail="broad-similarity-answer" if ok else "still-single-pair-answer",
        )
    )

    payload, _ = _run_case(
        session,
        args.base_url,
        args.model,
        "What is the largest document i have uploaded?",
        [],
    )
    reply = str(payload.get("reply", ""))
    ok = str(largest_document.get("original_name", "")) in reply and any(unit in reply for unit in ("KB", "MB", "GB", "B"))
    results.append(
        _result(
            key="largest_document",
            question="What is the largest document i have uploaded?",
            payload=payload,
            ok=ok,
            detail="largest-doc-resolved" if ok else "largest-doc-mismatch",
        )
    )

    payload, _ = _run_case(
        session,
        args.base_url,
        args.model,
        "When did i upload my latest document?",
        [],
    )
    reply = str(payload.get("reply", ""))
    ok = str(latest_document.get("original_name", "")) in reply and str(latest_document.get("uploaded_at", ""))[:10] in reply
    results.append(
        _result(
            key="latest_upload_time",
            question="When did i upload my latest document?",
            payload=payload,
            ok=ok,
            detail="upload-time-resolved" if ok else "upload-time-mismatch",
        )
    )

    payload, history = _run_case(
        session,
        args.base_url,
        args.model,
        f"What is {invoice_document['original_name']} about?",
        [],
    )
    reply = str(payload.get("reply", "")).lower()
    ok = "invoice" in reply
    results.append(
        _result(
            key="invoice_summary",
            question=f"What is {invoice_document['original_name']} about?",
            payload=payload,
            ok=ok,
            detail="invoice-recognized" if ok else "invoice-not-recognized",
        )
    )

    payload, history = _run_case(
        session,
        args.base_url,
        args.model,
        "Is that an invoice?",
        history,
    )
    reply = str(payload.get("reply", "")).lower()
    ok = reply.startswith("yes") and str(invoice_document.get("original_name", "")).lower() in reply
    results.append(
        _result(
            key="invoice_followup_confirmation",
            question="Is that an invoice?",
            payload=payload,
            ok=ok,
            detail="followup-kept-target" if ok else "followup-lost-target",
        )
    )

    payload, history = _run_case(
        session,
        args.base_url,
        args.model,
        "From what company?",
        history,
    )
    reply = str(payload.get("reply", ""))
    ok = any(company in reply for company in invoice_companies[:2]) if invoice_companies else bool(reply.strip())
    results.append(
        _result(
            key="invoice_company_followup",
            question="From what company?",
            payload=payload,
            ok=ok,
            detail="company-resolved" if ok else "company-missing",
        )
    )

    payload, history = _run_case(
        session,
        args.base_url,
        args.model,
        "What products did i order in that invoice?",
        history,
    )
    reply = str(payload.get("reply", ""))
    ok = any(product in reply for product in invoice_products[:1]) if invoice_products else "could not find a clear product list" in reply.lower()
    results.append(
        _result(
            key="invoice_products_followup",
            question="What products did i order in that invoice?",
            payload=payload,
            ok=ok,
            detail="product-resolved" if ok else "product-missing",
        )
    )

    payload, _ = _run_case(
        session,
        args.base_url,
        args.model,
        "Do i have any uploaded invoices?",
        [],
    )
    reply = str(payload.get("reply", ""))
    ok = str(invoice_document.get("original_name", "")) in reply and "invoice" in reply.lower()
    results.append(
        _result(
            key="invoice_inventory",
            question="Do i have any uploaded invoices?",
            payload=payload,
            ok=ok,
            detail="invoice-list-present" if ok else "invoice-list-missing",
        )
    )

    payload, _ = _run_case(
        session,
        args.base_url,
        args.model,
        "Can you check the other invoices and see if there is any information about what products i have ordered?",
        history,
    )
    reply = str(payload.get("reply", "")).lower()
    ok = "only one document" not in reply and "one document was provided" not in reply
    results.append(
        _result(
            key="other_invoices_products",
            question="Can you check the other invoices and see if there is any information about what products i have ordered?",
            payload=payload,
            ok=ok,
            detail="multi-invoice-scan" if ok else "collapsed-to-single-document",
        )
    )

    payload, _ = _run_case(
        session,
        args.base_url,
        args.model,
        "Do i have any signed documents?",
        [],
    )
    reply = str(payload.get("reply", "")).lower()
    ok = "do not contain information" not in reply and "provided documents do not contain information" not in reply
    results.append(
        _result(
            key="signed_documents",
            question="Do i have any signed documents?",
            payload=payload,
            ok=ok,
            detail="signature-answer-grounded" if ok else "signature-answer-too-absolute",
        )
    )

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
    _write_report(report_md, metadata, results)

    for result in results:
        print(f"[{'PASS' if result.ok else 'FAIL'}] {result.key}: {result.detail}")

    print(f"Markdown report: {report_md}")
    print(f"JSON report: {report_json}")
    return 0 if metadata["passed"] == metadata["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
