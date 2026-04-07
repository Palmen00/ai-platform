from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "temp" / "system-stability"


@dataclass
class CheckResult:
    step: str
    ok: bool
    detail: str
    payload: dict[str, Any] | None = None


@dataclass
class PerfSample:
    name: str
    count: int
    min_ms: float
    avg_ms: float
    p95_ms: float
    max_ms: float


class SuiteFailure(RuntimeError):
    pass


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _json_or_empty(response: requests.Response) -> dict[str, Any]:
    if not response.content:
        return {}
    return response.json()


def _ensure_ok(response: requests.Response, context: str) -> dict[str, Any]:
    if not response.ok:
        raise SuiteFailure(f"{context} failed: {response.status_code} {response.text[:500]}")
    return _json_or_empty(response)


def _login(session: requests.Session, base_url: str, username: str, password: str) -> None:
    response = session.post(
        f"{base_url}/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    _ensure_ok(response, "login")


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: int = 120,
    **kwargs,
) -> dict[str, Any]:
    response = session.request(method, url, timeout=timeout, **kwargs)
    return _ensure_ok(response, f"{method} {url}")


def _run_script(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _measure(name: str, fn, runs: int) -> PerfSample:
    latencies: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        fn()
        latencies.append((time.perf_counter() - started) * 1000.0)

    latencies_sorted = sorted(latencies)
    p95_index = max(0, min(len(latencies_sorted) - 1, round(len(latencies_sorted) * 0.95) - 1))
    return PerfSample(
        name=name,
        count=len(latencies_sorted),
        min_ms=round(min(latencies_sorted), 1),
        avg_ms=round(statistics.fmean(latencies_sorted), 1),
        p95_ms=round(latencies_sorted[p95_index], 1),
        max_ms=round(max(latencies_sorted), 1),
    )


def _find_document(documents: list[dict[str, Any]], *, provider: str | None = None, origin: str | None = None) -> dict[str, Any] | None:
    for document in documents:
        if provider and document.get("source_provider") != provider:
            continue
        if origin and document.get("source_origin") != origin:
            continue
        if document.get("processing_status") != "processed":
            continue
        if document.get("indexing_status") != "indexed":
            continue
        return document
    return None


def _find_matching_document(
    documents: list[dict[str, Any]],
    *,
    provider: str,
    origin: str,
    original_name_contains: str | None = None,
    source_kind: str | None = None,
) -> dict[str, Any] | None:
    for document in documents:
        if document.get("source_provider") != provider:
            continue
        if document.get("source_origin") != origin:
            continue
        if document.get("processing_status") != "processed":
            continue
        if document.get("indexing_status") != "indexed":
            continue
        if source_kind and document.get("source_kind") != source_kind:
            continue
        if original_name_contains and original_name_contains.lower() not in str(document.get("original_name", "")).lower():
            continue
        return document
    return None


def _write_markdown(path: Path, metadata: dict[str, Any], checks: list[CheckResult], perf: list[PerfSample]) -> None:
    lines = [
        "# System Stability Report",
        "",
        f"- Timestamp: {metadata['timestamp']}",
        f"- Base URL: {metadata['base_url']}",
        f"- Server label: {metadata['server_label']}",
        "",
        "## Functional Checks",
        "",
    ]
    for item in checks:
        status = "PASS" if item.ok else "FAIL"
        lines.append(f"- `{status}` {item.step}: {item.detail}")

    lines.extend(["", "## Performance", ""])
    for sample in perf:
        lines.append(
            f"- `{sample.name}`: avg `{sample.avg_ms} ms`, p95 `{sample.p95_ms} ms`, "
            f"min `{sample.min_ms} ms`, max `{sample.max_ms} ms`, runs `{sample.count}`"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a broad Local AI OS system stability suite.")
    parser.add_argument("--base-url", default="http://192.168.1.105:8000")
    parser.add_argument("--username", default="Admin")
    parser.add_argument("--password", default="password")
    parser.add_argument("--server-label", default="ai@192.168.1.105")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    report_md = args.output_dir / f"system-stability-{stamp}.md"
    report_json = args.output_dir / f"system-stability-{stamp}.json"

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    checks: list[CheckResult] = []
    perf: list[PerfSample] = []
    metadata: dict[str, Any] = {
        "timestamp": stamp,
        "base_url": args.base_url,
        "server_label": args.server_label,
    }

    try:
        health = _request_json(session, "GET", f"{args.base_url}/health", timeout=30)
        checks.append(CheckResult("health", health.get("status") == "ok", f"Health returned {health.get('status')}.", health))

        _login(session, args.base_url, args.username, args.password)
        checks.append(CheckResult("login", True, "Admin login succeeded."))

        auth_status = _request_json(session, "GET", f"{args.base_url}/auth/status", timeout=30)
        checks.append(
            CheckResult(
                "auth_status",
                bool(auth_status.get("authenticated")),
                (
                    f"Auth enabled={auth_status.get('auth_enabled')}, "
                    f"authenticated={auth_status.get('authenticated')}."
                ),
                auth_status,
            )
        )

        models_payload = _request_json(session, "GET", f"{args.base_url}/models", timeout=60)
        checks.append(
            CheckResult(
                "models",
                len(models_payload.get("models", [])) > 0,
                f"Model endpoint returned {len(models_payload.get('models', []))} model entries.",
                {"model_count": len(models_payload.get("models", []))},
            )
        )

        documents_payload = _request_json(
            session,
            "GET",
            f"{args.base_url}/documents",
            params={"limit": 200, "offset": 0},
            timeout=60,
        )
        documents = documents_payload.get("documents", [])
        checks.append(
            CheckResult(
                "documents_list",
                len(documents) > 0,
                f"Documents endpoint returned {len(documents)} documents.",
                {"total_count": documents_payload.get("total_count", 0)},
            )
        )

        conversations_payload = _request_json(session, "GET", f"{args.base_url}/conversations", timeout=60)
        checks.append(
            CheckResult(
                "conversations_list",
                True,
                f"Conversations endpoint returned {len(conversations_payload.get('conversations', []))} conversations.",
                {"conversation_count": len(conversations_payload.get("conversations", []))},
            )
        )

        sharepoint_document = _find_matching_document(
            documents,
            provider="sharepoint",
            origin="connector",
            original_name_contains="policy",
            source_kind="word",
        ) or _find_document(documents, provider="sharepoint", origin="connector")
        google_drive_document = _find_document(documents, provider="google_drive", origin="connector")

        if sharepoint_document:
            preview = _request_json(
                session,
                "GET",
                f"{args.base_url}/documents/{sharepoint_document['id']}/preview",
                timeout=60,
            )
            extracted = preview.get("preview", {}).get("extracted_text", "")
            checks.append(
                CheckResult(
                    "sharepoint_preview",
                    bool(extracted.strip()),
                    f"Preview returned {len(extracted)} characters for {sharepoint_document['original_name']}.",
                    {"document_id": sharepoint_document["id"]},
                )
            )

            chat_payload = _request_json(
                session,
                "POST",
                f"{args.base_url}/chat",
                json={
                    "message": "What is the policy title?",
                    "document_ids": [sharepoint_document["id"]],
                    "persist_conversation": False,
                },
                timeout=180,
            )
            reply = str(chat_payload.get("reply", ""))
            checks.append(
                CheckResult(
                    "sharepoint_chat",
                    "Retention Policy Aurora".lower() in reply.lower(),
                    f"SharePoint-grounded chat returned {len(reply)} characters.",
                    {"document_id": sharepoint_document["id"], "reply": reply},
                )
            )
        else:
            checks.append(CheckResult("sharepoint_document_present", False, "No indexed SharePoint connector document was found."))

        if google_drive_document:
            preview = _request_json(
                session,
                "GET",
                f"{args.base_url}/documents/{google_drive_document['id']}/preview",
                timeout=60,
            )
            extracted = preview.get("preview", {}).get("extracted_text", "")
            checks.append(
                CheckResult(
                    "google_drive_preview",
                    bool(extracted.strip()),
                    f"Preview returned {len(extracted)} characters for {google_drive_document['original_name']}.",
                    {"document_id": google_drive_document["id"]},
                )
            )

            chat_payload = _request_json(
                session,
                "POST",
                f"{args.base_url}/chat",
                json={
                    "message": "Summarize the main point of this document in one sentence.",
                    "document_ids": [google_drive_document["id"]],
                    "persist_conversation": False,
                },
                timeout=180,
            )
            reply = str(chat_payload.get("reply", ""))
            checks.append(
                CheckResult(
                    "google_drive_chat",
                    len(reply.strip()) > 20,
                    f"Drive-grounded chat returned {len(reply)} characters.",
                    {"document_id": google_drive_document["id"]},
                )
            )
        else:
            checks.append(CheckResult("google_drive_document_present", False, "No indexed Google Drive connector document was found."))

        sharepoint_script = _run_script(
            [
                sys.executable,
                str(ROOT / "scripts" / "tests" / "run_sharepoint_mock_smoke.py"),
                "--base-url",
                args.base_url,
                "--username",
                args.username,
                "--password",
                args.password,
            ],
            ROOT,
        )
        checks.append(
            CheckResult(
                "sharepoint_mock_smoke",
                sharepoint_script.returncode == 0,
                "SharePoint mock smoke script passed." if sharepoint_script.returncode == 0 else sharepoint_script.stdout[-800:],
                {
                    "returncode": sharepoint_script.returncode,
                    "stdout_tail": sharepoint_script.stdout[-1200:],
                    "stderr_tail": sharepoint_script.stderr[-1200:],
                },
            )
        )

        upload_script = _run_script(
            [
                sys.executable,
                str(ROOT / "scripts" / "tests" / "run_upload_ocr_e2e.py"),
                "--base-url",
                args.base_url,
                "--username",
                args.username,
                "--password",
                args.password,
            ],
            ROOT,
        )
        checks.append(
            CheckResult(
                "upload_ocr_e2e",
                upload_script.returncode == 0,
                "Upload/OCR E2E script passed." if upload_script.returncode == 0 else upload_script.stdout[-800:],
                {
                    "returncode": upload_script.returncode,
                    "stdout_tail": upload_script.stdout[-1200:],
                    "stderr_tail": upload_script.stderr[-1200:],
                },
            )
        )

        perf.append(
            _measure(
                "health",
                lambda: _request_json(session, "GET", f"{args.base_url}/health", timeout=30),
                runs=10,
            )
        )
        perf.append(
            _measure(
                "auth_status",
                lambda: _request_json(session, "GET", f"{args.base_url}/auth/status", timeout=30),
                runs=10,
            )
        )
        perf.append(
            _measure(
                "documents_list",
                lambda: _request_json(
                    session,
                    "GET",
                    f"{args.base_url}/documents",
                    params={"limit": 50, "offset": 0},
                    timeout=60,
                ),
                runs=5,
            )
        )
        perf.append(
            _measure(
                "conversations_list",
                lambda: _request_json(session, "GET", f"{args.base_url}/conversations", timeout=60),
                runs=5,
            )
        )
        perf.append(
            _measure(
                "runtime_chat",
                lambda: _request_json(
                    session,
                    "POST",
                    f"{args.base_url}/chat",
                    json={
                        "message": "Vad är det för dag idag och vilken vecka är det?",
                        "persist_conversation": False,
                    },
                    timeout=120,
                ),
                runs=3,
            )
        )

        if sharepoint_document:
            perf.append(
                _measure(
                    "grounded_chat_sharepoint",
                    lambda: _request_json(
                        session,
                        "POST",
                        f"{args.base_url}/chat",
                        json={
                            "message": "What is the policy title?",
                            "document_ids": [sharepoint_document["id"]],
                            "persist_conversation": False,
                        },
                        timeout=180,
                    ),
                    runs=3,
                )
            )

        preview_browse = _request_json(
            session,
            "POST",
            f"{args.base_url}/connectors/browse",
            json={"provider": "google_drive", "auth_mode": "drive"},
            timeout=120,
        )
        checks.append(
            CheckResult(
                "google_drive_browse",
                len(preview_browse.get("folders", [])) > 0,
                f"Google Drive browse returned {len(preview_browse.get('folders', []))} folders.",
                {"folder_count": len(preview_browse.get("folders", []))},
            )
        )
        perf.append(
            _measure(
                "google_drive_browse",
                lambda: _request_json(
                    session,
                    "POST",
                    f"{args.base_url}/connectors/browse",
                    json={"provider": "google_drive", "auth_mode": "drive"},
                    timeout=120,
                ),
                runs=3,
            )
        )

    except Exception as exc:  # noqa: BLE001
        checks.append(CheckResult("fatal", False, str(exc)))

    payload = {
        "metadata": metadata,
        "checks": [asdict(item) for item in checks],
        "performance": [asdict(item) for item in perf],
    }
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(report_md, metadata, checks, perf)

    print(f"Markdown report: {report_md}")
    print(f"JSON report: {report_json}")

    failed = [item for item in checks if not item.ok]
    if failed:
        print("System stability suite failed.")
        return 1

    print("System stability suite passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
