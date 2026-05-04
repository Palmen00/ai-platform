from __future__ import annotations

import argparse
import json
import os
import re
import sys
import textwrap
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "temp" / "invoice-document-qa"


class TestFailure(RuntimeError):
    pass


@dataclass
class InvoiceFixture:
    key: str
    filename: str
    vendor: str
    invoice_number: str
    invoice_date: str
    due_date: str
    total: str
    currency: str
    products: list[str]


@dataclass
class InvoiceResult:
    key: str
    question: str
    ok: bool
    detail: str
    reply: str
    source_names: list[str]
    expected_terms: list[str]


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _contains_terms(reply: str, terms: list[str]) -> bool:
    normalized_reply = _normalize(reply)
    digit_reply = re.sub(r"\D+", "", reply)
    numeric_values = [
        float(match.group(0).replace(",", "."))
        for match in re.finditer(r"\d+(?:[.,]\d+)?", reply)
    ]
    for term in terms:
        if term.lower() in reply.lower():
            continue
        normalized_term = _normalize(term)
        if normalized_term and normalized_term in normalized_reply:
            continue
        digit_term = re.sub(r"\D+", "", term)
        if digit_term and digit_term in digit_reply:
            continue
        if re.fullmatch(r"\d+(?:[.,]\d+)?", term):
            expected = float(term.replace(",", "."))
            if any(abs(value - expected) < 0.001 for value in numeric_values):
                continue
        return False
    return True


def _ensure_ok(response: requests.Response, context: str) -> dict[str, Any]:
    if not response.ok:
        raise TestFailure(f"{context} failed: {response.status_code} {response.text[:500]}")
    if not response.content:
        return {}
    return response.json()


def _login(session: requests.Session, base_url: str, username: str, password: str) -> None:
    _ensure_ok(
        session.post(
            f"{base_url}/auth/login",
            json={"username": username, "password": password},
            timeout=30,
        ),
        "login",
    )


def _pick_model(session: requests.Session, base_url: str) -> str | None:
    response = session.get(f"{base_url}/models", timeout=30)
    if not response.ok:
        return None
    models = response.json().get("models") or []
    installed_chat_models = [
        model
        for model in models
        if model.get("capability") == "chat" and model.get("installed")
    ]
    if installed_chat_models:
        return installed_chat_models[0].get("name")
    chat_models = [model for model in models if model.get("capability") == "chat"]
    if chat_models:
        return chat_models[0].get("name")
    return models[0].get("name") if models else None


def _build_fixtures(base_dir: Path, run_id: str) -> list[tuple[InvoiceFixture, Path]]:
    base_dir.mkdir(parents=True, exist_ok=True)
    fixtures = [
        InvoiceFixture(
            key="office",
            filename=f"{run_id}-invoice-aurora-office.txt",
            vendor="NordOffice AB",
            invoice_number="INV-AURORA-2026-041",
            invoice_date="2026-04-18",
            due_date="2026-05-02",
            total="6368.75",
            currency="SEK",
            products=["ErgoChair Pro", "Cable Dock USB-C", "Whiteboard Markers"],
        ),
        InvoiceFixture(
            key="bike",
            filename=f"{run_id}-invoice-peak-velo.txt",
            vendor="Peak Velo Ltd",
            invoice_number="PV-2026-118",
            invoice_date="2026-04-21",
            due_date="2026-05-05",
            total="1942.50",
            currency="SEK",
            products=["Carbon Brake Pads", "Workshop Tune-up"],
        ),
    ]

    bodies = {
        "office": """
            Invoice
            Vendor: NordOffice AB
            Customer: Oskar Palm
            Invoice No: INV-AURORA-2026-041
            Invoice Date: 2026-04-18
            Due Date: 2026-05-02
            Currency: SEK

            Item | SKU | Quantity | Unit Price | Total
            ErgoChair Pro | ECO-CHAIR-9 | 2 | 1995.00 | 3990.00
            Cable Dock USB-C | DOCK-USB-C | 1 | 749.00 | 749.00
            Whiteboard Markers | MARK-12 | 5 | 68.00 | 340.00

            Subtotal: 5079.00
            Tax: 1289.75
            Total: 6368.75 SEK
            Notes: Order for workspace equipment.
        """,
        "bike": """
            Faktura
            Vendor: Peak Velo Ltd
            Customer: Oskar Palm
            Invoice No: PV-2026-118
            Invoice Date: 2026-04-21
            Due Date: 2026-05-05
            Currency: SEK

            Description | SKU | Qty | Unit Price | Line Total
            Carbon Brake Pads | BRK-CARBON-22 | 3 | 249.50 | 748.50
            Workshop Tune-up | SERVICE-TUNE | 1 | 805.50 | 805.50

            Subtotal: 1554.00
            Tax: 388.50
            Total: 1942.50 SEK
            Notes: Bicycle maintenance order.
        """,
    }

    paths: list[tuple[InvoiceFixture, Path]] = []
    for fixture in fixtures:
        path = base_dir / fixture.filename
        path.write_text(
            textwrap.dedent(bodies[fixture.key]).strip() + f"\nBatch: {run_id}\n",
            encoding="utf-8",
        )
        paths.append((fixture, path))
    return paths


def _upload(session: requests.Session, base_url: str, path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        response = session.post(
            f"{base_url}/documents/upload",
            files={"file": (path.name, handle, "text/plain")},
            timeout=120,
        )
    return _ensure_ok(response, f"upload:{path.name}")["document"]


def _list_documents(session: requests.Session, base_url: str) -> list[dict[str, Any]]:
    payload = _ensure_ok(
        session.get(f"{base_url}/documents", params={"limit": 500, "offset": 0}, timeout=60),
        "documents",
    )
    return list(payload.get("documents", []))


def _wait_for_document(
    session: requests.Session,
    base_url: str,
    document_id: str,
    *,
    timeout_seconds: int = 240,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_seen: dict[str, Any] | None = None
    while time.time() < deadline:
        for document in _list_documents(session, base_url):
            if document.get("id") != document_id:
                continue
            last_seen = document
            if (
                document.get("processing_status") == "processed"
                and document.get("indexing_status") == "indexed"
            ):
                return document
            if document.get("processing_status") == "failed":
                raise TestFailure(f"Document processing failed: {json.dumps(document, ensure_ascii=False)}")
        time.sleep(3)
    raise TestFailure(
        f"Timed out waiting for {document_id}. Last state: {json.dumps(last_seen or {}, ensure_ascii=False)}"
    )


def _ask(
    session: requests.Session,
    base_url: str,
    model: str | None,
    question: str,
    document_ids: list[str] | None = None,
) -> dict[str, Any]:
    return _ensure_ok(
        session.post(
            f"{base_url}/chat",
            json={
                "message": question,
                "model": model,
                "history": [],
                "document_ids": document_ids or [],
                "persist_conversation": False,
            },
            timeout=180,
        ),
        f"chat:{question}",
    )


def _result(
    *,
    key: str,
    question: str,
    payload: dict[str, Any],
    expected_terms: list[str],
    expected_source_fragments: list[str],
) -> InvoiceResult:
    reply = str(payload.get("reply", ""))
    source_names = [
        str(source.get("document_name", ""))
        for source in payload.get("sources", [])
        if source.get("document_name")
    ]
    lowered_sources = [name.lower() for name in source_names]
    lowered_reply = reply.lower()
    source_ok = all(
        any(fragment.lower() in source for source in lowered_sources)
        or fragment.lower() in lowered_reply
        for fragment in expected_source_fragments
    )
    reply_ok = _contains_terms(reply, expected_terms)
    return InvoiceResult(
        key=key,
        question=question,
        ok=reply_ok and source_ok,
        detail=", ".join(
            [
                "reply-match" if reply_ok else "reply-mismatch",
                "source-match" if source_ok else "source-mismatch",
            ]
        ),
        reply=reply,
        source_names=source_names,
        expected_terms=expected_terms,
    )


def _validate_commercial_summary(document: dict[str, Any], fixture: InvoiceFixture) -> InvoiceResult:
    summary = document.get("commercial_summary") or {}
    line_items = summary.get("line_items") or []
    serialized = json.dumps(summary, ensure_ascii=False)
    expected_terms = [
        fixture.invoice_number,
        fixture.invoice_date,
        fixture.due_date,
        fixture.total,
        fixture.products[0],
    ]
    ok = document.get("detected_document_type") == "invoice" and bool(line_items) and _contains_terms(
        serialized,
        expected_terms,
    )
    return InvoiceResult(
        key=f"{fixture.key}_commercial_summary",
        question="metadata extraction",
        ok=ok,
        detail=f"type={document.get('detected_document_type')} items={len(line_items)}",
        reply=serialized,
        source_names=[str(document.get("original_name", ""))],
        expected_terms=expected_terms,
    )


def _delete_document(session: requests.Session, base_url: str, document_id: str) -> None:
    response = session.delete(f"{base_url}/documents/{document_id}", timeout=30)
    if response.status_code not in {200, 204}:
        raise TestFailure(f"Delete failed for {document_id}: {response.status_code} {response.text[:500]}")


def _write_report(path: Path, metadata: dict[str, Any], results: list[InvoiceResult]) -> None:
    passed = sum(1 for result in results if result.ok)
    lines = [
        "# Invoice Document QA Report",
        "",
        f"- Timestamp: {metadata['timestamp']}",
        f"- Base URL: {metadata['base_url']}",
        f"- Model: {metadata['model'] or 'default'}",
        f"- Passed: {passed}/{len(results)}",
        "",
        "## Results",
        "",
    ]
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        lines.append(f"- `{status}` {result.key}: {result.detail}")
        lines.append(f"  Question: {result.question}")
        lines.append(f"  Expected: {', '.join(result.expected_terms)}")
        lines.append(f"  Reply: {result.reply}")
        lines.append(f"  Sources: {', '.join(result.source_names) if result.source_names else 'none'}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    run_id = _stamp()
    fixture_dir = args.output_dir / f"fixtures-{run_id}"
    report_md = args.output_dir / f"invoice-document-qa-{run_id}.md"
    report_json = args.output_dir / f"invoice-document-qa-{run_id}.json"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    _login(session, args.base_url, args.username, args.password)
    model = args.model or _pick_model(session, args.base_url)

    uploaded: list[tuple[InvoiceFixture, dict[str, Any]]] = []
    results: list[InvoiceResult] = []

    for fixture, path in _build_fixtures(fixture_dir, run_id):
        upload = _upload(session, args.base_url, path)
        document = _wait_for_document(session, args.base_url, str(upload["id"]))
        uploaded.append((fixture, document))
        results.append(_validate_commercial_summary(document, fixture))

    for fixture, document in uploaded:
        document_id = str(document["id"])
        document_name = str(document["original_name"])
        question = f"What products did I order in {document_name}?"
        results.append(
            _result(
                key=f"{fixture.key}_products",
                question=question,
                payload=_ask(session, args.base_url, model, question, [document_id]),
                expected_terms=fixture.products[:2],
                expected_source_fragments=[document_name],
            )
        )

        question = f"What is the invoice number, invoice date, due date, and total for {document_name}?"
        results.append(
            _result(
                key=f"{fixture.key}_invoice_facts",
                question=question,
                payload=_ask(session, args.base_url, model, question, [document_id]),
                expected_terms=[
                    fixture.invoice_number,
                    fixture.invoice_date,
                    fixture.due_date,
                    fixture.total,
                ],
                expected_source_fragments=[document_name],
            )
        )

    bike_fixture, bike_document = next(item for item in uploaded if item[0].key == "bike")
    question = f"Which invoice mentions {bike_fixture.products[0]}?"
    results.append(
        _result(
            key="cross_invoice_product_lookup",
            question=question,
            payload=_ask(session, args.base_url, model, question),
            expected_terms=[str(bike_document["original_name"]), bike_fixture.products[0]],
            expected_source_fragments=[str(bike_document["original_name"])],
        )
    )

    question = f"List the ordered products across invoice batch {run_id}."
    all_products = [uploaded[0][0].products[0], uploaded[1][0].products[0]]
    results.append(
        _result(
            key="cross_invoice_product_inventory",
            question=question,
            payload=_ask(session, args.base_url, model, question),
            expected_terms=all_products,
            expected_source_fragments=[],
        )
    )

    metadata = {
        "timestamp": run_id,
        "base_url": args.base_url,
        "model": model,
        "passed": sum(1 for result in results if result.ok),
        "total": len(results),
        "uploaded_documents": [document for _, document in uploaded],
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

    print(f"Markdown report: {report_md}")
    print(f"JSON report: {report_json}")
    for result in results:
        print(f"[{'PASS' if result.ok else 'FAIL'}] {result.key}: {result.detail}")

    if args.cleanup:
        for _, document in uploaded:
            _delete_document(session, args.base_url, str(document["id"]))

    return 0 if metadata["passed"] == metadata["total"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run invoice/product QA checks against Local AI OS.")
    parser.add_argument("--base-url", default=os.getenv("LOCAL_AI_OS_BASE_URL", "http://192.168.1.105:8000"))
    parser.add_argument("--username", default=os.getenv("LOCAL_AI_OS_USERNAME", "Admin"))
    parser.add_argument("--password", default=os.getenv("LOCAL_AI_OS_PASSWORD", "password"))
    parser.add_argument("--model", default=os.getenv("LOCAL_AI_OS_MODEL", ""))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--cleanup", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    sys.exit(run(parse_args()))
