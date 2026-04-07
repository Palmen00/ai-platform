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
DEFAULT_OUTPUT_DIR = ROOT / "temp" / "sharepoint-mock-smoke"


@dataclass
class SmokeQuestion:
    filename_suffix: str
    question: str
    expected_substring: str
    label: str


@dataclass
class SmokeResult:
    step: str
    ok: bool
    detail: str
    payload: dict[str, Any] | None = None


QUESTIONS: list[SmokeQuestion] = [
    SmokeQuestion(
        filename_suffix="policy.docx",
        question="What is the policy title?",
        expected_substring="Retention Policy Aurora",
        label="docx",
    ),
    SmokeQuestion(
        filename_suffix="metrics.xlsx",
        question="What is the Q2 total value in this spreadsheet?",
        expected_substring="982",
        label="xlsx",
    ),
    SmokeQuestion(
        filename_suffix="roadmap.pptx",
        question="What milestone name appears in this presentation?",
        expected_substring="Orion Launch",
        label="pptx",
    ),
    SmokeQuestion(
        filename_suffix="scan-pdf.pdf",
        question="What incident code appears in the scanned PDF?",
        expected_substring="INC-2048",
        label="pdf_ocr",
    ),
]


class SmokeFailure(RuntimeError):
    pass


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _ensure_ok(response: requests.Response, context: str) -> dict[str, Any]:
    if not response.ok:
        raise SmokeFailure(f"{context} failed: {response.status_code} {response.text[:500]}")
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


def _fetch_json(session: requests.Session, method: str, url: str, **kwargs) -> dict[str, Any]:
    response = session.request(method, url, timeout=kwargs.pop("timeout", 90), **kwargs)
    return _ensure_ok(response, f"{method} {url}")


def _delete_existing_connectors(session: requests.Session, base_url: str, target_name: str) -> int:
    payload = _fetch_json(session, "GET", f"{base_url}/connectors")
    deleted = 0
    for connector in payload.get("connectors", []):
        if connector.get("name") == target_name:
            _fetch_json(session, "DELETE", f"{base_url}/connectors/{connector['id']}")
            deleted += 1
    return deleted


def _wait_for_preview(
    session: requests.Session,
    base_url: str,
    document_id: str,
    *,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_error = "preview polling did not start"
    while time.time() < deadline:
        response = session.get(f"{base_url}/documents/{document_id}/preview", timeout=45)
        if response.ok:
            payload = response.json()
            extracted = payload.get("preview", {}).get("extracted_text", "")
            if extracted.strip():
                return payload
            last_error = "preview returned empty extracted text"
        else:
            last_error = f"{response.status_code} {response.text[:200]}"
        time.sleep(2.0)
    raise SmokeFailure(f"preview polling timed out for {document_id}: {last_error}")


def _contains(text: str, expected: str) -> bool:
    return expected.lower() in text.lower()


def _write_report(report_path: Path, results: list[SmokeResult], metadata: dict[str, Any]) -> None:
    lines = [
        "# SharePoint Mock Smoke Test",
        "",
        f"- Timestamp: {metadata['timestamp']}",
        f"- Base URL: {metadata['base_url']}",
        f"- Root path: `{metadata['root_path']}`",
        f"- Connector name: {metadata['connector_name']}",
        f"- Imported documents: {metadata.get('imported_count', 0)}",
        "",
        "## Results",
        "",
    ]
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        lines.append(f"- `{status}` {result.step}: {result.detail}")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a SharePoint mock/local smoke test.")
    parser.add_argument("--base-url", default="http://192.168.1.105:8000")
    parser.add_argument("--username", default="Admin")
    parser.add_argument("--password", default="password")
    parser.add_argument("--root-path", default="/app/data/sharepoint-smoke/library")
    parser.add_argument("--connector-name", default="SharePoint Mock Smoke")
    parser.add_argument("--container", default="sharepoint-smoke")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    report_md = args.output_dir / f"sharepoint-mock-smoke-{stamp}.md"
    report_json = args.output_dir / f"sharepoint-mock-smoke-{stamp}.json"

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    results: list[SmokeResult] = []
    metadata: dict[str, Any] = {
        "timestamp": stamp,
        "base_url": args.base_url,
        "root_path": args.root_path,
        "connector_name": args.connector_name,
    }

    try:
        _login(session, args.base_url, args.username, args.password)
        results.append(SmokeResult("login", True, "Admin session created."))

        deleted = _delete_existing_connectors(session, args.base_url, args.connector_name)
        results.append(
            SmokeResult(
                "cleanup",
                True,
                f"Deleted {deleted} previous connector(s) with the same smoke-test name.",
                {"deleted_connectors": deleted},
            )
        )

        browse_payload = _fetch_json(
            session,
            "POST",
            f"{args.base_url}/connectors/browse",
            json={
                "provider": "sharepoint",
                "auth_mode": "mock",
                "root_path": args.root_path,
            },
        )
        folders = browse_payload.get("folders", [])
        folder_names = [folder.get("name", "") for folder in folders]
        results.append(
            SmokeResult(
                "browse",
                {"Policies", "Reports", "Scans"}.issubset(set(folder_names)),
                f"Browse returned folders: {', '.join(folder_names)}",
                {"folder_count": len(folders)},
            )
        )

        create_payload = _fetch_json(
            session,
            "POST",
            f"{args.base_url}/connectors",
            json={
                "name": args.connector_name,
                "provider": "sharepoint",
                "enabled": True,
                "auth_mode": "mock",
                "root_path": args.root_path,
                "container": args.container,
                "provider_settings": {"max_files": "10"},
            },
        )
        connector = create_payload["connector"]
        connector_id = connector["id"]
        metadata["connector_id"] = connector_id
        results.append(
            SmokeResult(
                "create_connector",
                True,
                f"Created connector {connector_id}.",
                {"connector_id": connector_id},
            )
        )

        preview_sync = _fetch_json(
            session,
            "POST",
            f"{args.base_url}/connectors/{connector_id}/sync",
            params={"dry_run": "true"},
        )
        preview_total = (
            preview_sync.get("imported_count", 0)
            + preview_sync.get("updated_count", 0)
            + preview_sync.get("skipped_count", 0)
        )
        results.append(
            SmokeResult(
                "preview_sync",
                preview_sync.get("scanned_count", 0) >= 4 and preview_total >= 4,
                (
                    f"Preview scanned {preview_sync.get('scanned_count', 0)} file(s), "
                    f"would import {preview_sync.get('imported_count', 0)}, "
                    f"would update {preview_sync.get('updated_count', 0)}, "
                    f"would skip {preview_sync.get('skipped_count', 0)}."
                ),
                preview_sync,
            )
        )

        real_sync = _fetch_json(
            session,
            "POST",
            f"{args.base_url}/connectors/{connector_id}/sync",
        )
        imported_results = real_sync.get("results", [])
        sync_total = (
            real_sync.get("imported_count", 0)
            + real_sync.get("updated_count", 0)
            + real_sync.get("skipped_count", 0)
        )
        metadata["imported_count"] = real_sync.get("imported_count", 0)
        results.append(
            SmokeResult(
                "real_sync",
                real_sync.get("scanned_count", 0) >= 4
                and sync_total >= 4
                and len(imported_results) >= 4
                and all(item.get("document_id") for item in imported_results),
                (
                    f"Sync scanned {real_sync.get('scanned_count', 0)} file(s), "
                    f"imported {real_sync.get('imported_count', 0)}, "
                    f"updated {real_sync.get('updated_count', 0)}, "
                    f"skipped {real_sync.get('skipped_count', 0)}."
                ),
                real_sync,
            )
        )

        by_filename: dict[str, dict[str, Any]] = {
            item.get("original_name", ""): item for item in imported_results if item.get("original_name")
        }

        for question in QUESTIONS:
            matching = None
            for original_name, item in by_filename.items():
                if original_name.endswith(question.filename_suffix):
                    matching = item
                    break
            if not matching or not matching.get("document_id"):
                raise SmokeFailure(f"No synced document matched suffix '{question.filename_suffix}'.")

            document_id = matching["document_id"]
            preview = _wait_for_preview(session, args.base_url, document_id)
            preview_text = preview.get("preview", {}).get("extracted_text", "")
            results.append(
                SmokeResult(
                    f"preview_{question.label}",
                    bool(preview_text.strip()),
                    f"Preview extracted {len(preview_text)} characters for {matching['original_name']}.",
                    {
                        "document_id": document_id,
                        "original_name": matching["original_name"],
                        "character_count": len(preview_text),
                    },
                )
            )

            chat_payload = _fetch_json(
                session,
                "POST",
                f"{args.base_url}/chat",
                json={
                    "message": question.question,
                    "document_ids": [document_id],
                    "persist_conversation": False,
                },
                timeout=180,
            )
            reply = str(chat_payload.get("reply", "")).strip()
            ok = _contains(reply, question.expected_substring)
            results.append(
                SmokeResult(
                    f"chat_{question.label}",
                    ok,
                    (
                        f"Asked '{question.question}' and received "
                        f"{len(reply)} characters."
                    ),
                    {
                        "document_id": document_id,
                        "expected": question.expected_substring,
                        "reply": reply,
                        "retrieval": chat_payload.get("retrieval"),
                    },
                )
            )

    except Exception as exc:  # noqa: BLE001
        results.append(SmokeResult("fatal", False, str(exc)))

    report_payload = {
        "metadata": metadata,
        "results": [asdict(result) for result in results],
    }
    report_json.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_report(report_md, results, metadata)

    failed = [result for result in results if not result.ok]
    print(f"Markdown report: {report_md}")
    print(f"JSON report: {report_json}")
    if failed:
        print("Smoke test failed.")
        return 1

    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
