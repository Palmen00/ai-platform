from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "temp" / "production-hardening"


@dataclass
class HardeningCheck:
    key: str
    severity: str
    ok: bool
    detail: str
    evidence: dict[str, Any] | None = None


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: int = 60,
    **kwargs: Any,
) -> tuple[requests.Response, dict[str, Any]]:
    response = session.request(method, url, timeout=timeout, **kwargs)
    payload = response.json() if response.content else {}
    return response, payload


def _git_lines(args: list[str]) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _tracked_secret_filename_hits() -> list[str]:
    tracked = _git_lines(["ls-files"])
    suspicious_patterns = (
        r"(^|/)\.env$",
        r"(^|/)\.env\.",
        r"client_secret.*\.json$",
        r"token\.json$",
        r"refresh_token",
        r"id_rsa$",
        r"id_ed25519$",
        r"\.pem$",
        r"\.p12$",
        r"\.key$",
    )
    allowlist = (
        ".env.example",
        ".env.ubuntu.example",
        "answer-file.example.env",
        "answer-file.standard.env",
    )
    hits: list[str] = []
    for path in tracked:
        normalized = path.replace("\\", "/")
        if normalized.endswith(allowlist):
            continue
        if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in suspicious_patterns):
            hits.append(path)
    return hits


def _tracked_private_key_hits() -> list[str]:
    completed = subprocess.run(
        ["git", "grep", "-n", "BEGIN .*PRIVATE KEY"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode not in {0, 1}:
        return [completed.stderr.strip()]
    allowlist_paths = {
        "scripts/tests/run_ai_capability_suite.py",
    }
    hits: list[str] = []
    for line in completed.stdout.splitlines():
        normalized_path = line.split(":", 1)[0].replace("\\", "/")
        if normalized_path in allowlist_paths:
            continue
        if "BEGIN .*PRIVATE KEY" in line:
            continue
        hits.append(line)
    return [
        line
        for line in hits
    ]


def _write_reports(
    *,
    output_dir: Path,
    metadata: dict[str, Any],
    checks: list[HardeningCheck],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = metadata["timestamp"]
    md_path = output_dir / f"production-hardening-{stamp}.md"
    json_path = output_dir / f"production-hardening-{stamp}.json"

    critical_failed = [check for check in checks if check.severity == "critical" and not check.ok]
    warning_failed = [check for check in checks if check.severity == "warning" and not check.ok]
    payload = {
        "metadata": metadata,
        "summary": {
            "passed": sum(1 for check in checks if check.ok),
            "total": len(checks),
            "critical_failed": len(critical_failed),
            "warning_failed": len(warning_failed),
        },
        "checks": [asdict(check) for check in checks],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"# Production Hardening Check {stamp}",
        "",
        f"- Base URL: `{metadata['base_url']}`",
        f"- Critical failed: `{len(critical_failed)}`",
        f"- Warnings: `{len(warning_failed)}`",
        "",
        "## Checks",
        "",
    ]
    for check in checks:
        status = "PASS" if check.ok else ("FAIL" if check.severity == "critical" else "WARN")
        lines.append(f"- `{status}` `{check.key}` ({check.severity}): {check.detail}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run safe production-hardening checks against Local AI OS.")
    parser.add_argument("--base-url", default=os.getenv("LOCAL_AI_OS_BASE_URL", "http://192.168.1.105:8000"))
    parser.add_argument("--username", default=os.getenv("LOCAL_AI_OS_USERNAME", "Admin"))
    parser.add_argument("--password", default=os.getenv("LOCAL_AI_OS_PASSWORD", "password"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    checks: list[HardeningCheck] = []

    auth_response, auth_status = _request_json(session, "GET", f"{args.base_url}/auth/status", timeout=30)
    checks.append(
        HardeningCheck(
            "auth_enabled_configured",
            "critical",
            auth_response.ok and bool(auth_status.get("auth_enabled")) and bool(auth_status.get("auth_configured")),
            (
                f"auth_enabled={auth_status.get('auth_enabled')} "
                f"auth_configured={auth_status.get('auth_configured')}"
            ),
            auth_status,
        )
    )

    bad_response, bad_payload = _request_json(
        session,
        "POST",
        f"{args.base_url}/auth/login",
        json={"username": "__hardening_check_missing_user__", "password": "__bad_password__"},
        timeout=30,
    )
    checks.append(
        HardeningCheck(
            "generic_failed_login",
            "critical",
            bad_response.status_code == 401
            and "could not sign in" in str(bad_payload.get("detail", "")).lower(),
            f"failed login status={bad_response.status_code}",
            {"detail": bad_payload.get("detail")},
        )
    )

    login_response, login_payload = _request_json(
        session,
        "POST",
        f"{args.base_url}/auth/login",
        json={"username": args.username, "password": args.password, "remember_me": True},
        timeout=30,
    )
    set_cookie = login_response.headers.get("set-cookie", "")
    checks.append(
        HardeningCheck(
            "admin_login",
            "critical",
            login_response.ok and bool(login_payload.get("authenticated")),
            f"login status={login_response.status_code}",
            {"username": login_payload.get("username"), "role": login_payload.get("role")},
        )
    )
    checks.append(
        HardeningCheck(
            "session_cookie_flags",
            "critical",
            "httponly" in set_cookie.lower() and "samesite" in set_cookie.lower(),
            "Session cookie should be HttpOnly and SameSite-protected.",
            {"set_cookie": set_cookie.replace(args.password, "[redacted]")},
        )
    )
    checks.append(
        HardeningCheck(
            "session_cookie_secure_for_https",
            "warning",
            (not args.base_url.lower().startswith("https://")) or "secure" in set_cookie.lower(),
            "HTTPS deployments should set the Secure cookie flag.",
            {"base_url": args.base_url},
        )
    )

    status_response, status_payload = _request_json(session, "GET", f"{args.base_url}/status", timeout=60)
    storage = status_payload.get("storage") or {}
    checks.append(
        HardeningCheck(
            "dependency_status",
            "critical",
            status_response.ok
            and status_payload.get("status") == "ok"
            and (status_payload.get("ollama") or {}).get("status") == "ok"
            and (status_payload.get("qdrant") or {}).get("status") == "ok",
            f"status={status_payload.get('status')} ollama={(status_payload.get('ollama') or {}).get('status')} qdrant={(status_payload.get('qdrant') or {}).get('status')}",
            status_payload,
        )
    )
    checks.append(
        HardeningCheck(
            "no_failed_documents",
            "warning",
            int(storage.get("failed_documents") or 0) == 0,
            f"failed_documents={storage.get('failed_documents')}",
            storage,
        )
    )

    logs_response, logs_payload = _request_json(
        session,
        "GET",
        f"{args.base_url}/logs",
        params={"audit_only": "true", "event_limit": 20},
        timeout=60,
    )
    checks.append(
        HardeningCheck(
            "audit_log_available",
            "critical",
            logs_response.ok and isinstance(logs_payload.get("events"), list),
            f"audit events returned={len(logs_payload.get('events') or [])}",
            {"event_count": len(logs_payload.get("events") or [])},
        )
    )

    secret_filename_hits = _tracked_secret_filename_hits()
    private_key_hits = _tracked_private_key_hits()
    checks.append(
        HardeningCheck(
            "no_tracked_secret_filenames",
            "critical",
            not secret_filename_hits,
            "Tracked repository files should not include env files, OAuth client secret files, tokens, or key material.",
            {"hits": secret_filename_hits},
        )
    )
    checks.append(
        HardeningCheck(
            "no_tracked_private_keys",
            "critical",
            not private_key_hits,
            "Tracked repository content should not include private keys.",
            {"hits": private_key_hits[:20]},
        )
    )

    metadata = {
        "timestamp": _stamp(),
        "base_url": args.base_url,
        "environment": status_payload.get("environment"),
    }
    md_path, json_path = _write_reports(output_dir=args.output_dir, metadata=metadata, checks=checks)
    print(f"Markdown report: {md_path}")
    print(f"JSON report: {json_path}")

    critical_failed = [check.key for check in checks if check.severity == "critical" and not check.ok]
    print(json.dumps({"critical_failed": critical_failed, "total": len(checks)}, indent=2))
    return 0 if not critical_failed else 1


if __name__ == "__main__":
    sys.exit(main())
