from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import requests


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "temp" / "server-runtime-profile"


@dataclass
class LatencySample:
    name: str
    runs: int
    min_ms: float
    avg_ms: float
    p95_ms: float
    max_ms: float


@dataclass
class RemoteCommandResult:
    name: str
    ok: bool
    stdout: str
    stderr: str


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: int = 120,
    **kwargs: Any,
) -> dict[str, Any]:
    response = session.request(method, url, timeout=timeout, **kwargs)
    response.raise_for_status()
    return response.json() if response.content else {}


def _login(session: requests.Session, base_url: str, username: str, password: str) -> None:
    status = _request_json(session, "GET", f"{base_url}/auth/status", timeout=30)
    if not status.get("auth_enabled"):
        return
    _request_json(
        session,
        "POST",
        f"{base_url}/auth/login",
        json={"username": username, "password": password, "remember_me": True},
        timeout=30,
    )


def _measure(name: str, runs: int, fn: Callable[[], object]) -> LatencySample:
    latencies: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        fn()
        latencies.append((time.perf_counter() - started) * 1000.0)

    ordered = sorted(latencies)
    p95_index = max(0, min(len(ordered) - 1, round(len(ordered) * 0.95) - 1))
    return LatencySample(
        name=name,
        runs=runs,
        min_ms=round(min(ordered), 1),
        avg_ms=round(statistics.fmean(ordered), 1),
        p95_ms=round(ordered[p95_index], 1),
        max_ms=round(max(ordered), 1),
    )


def _run_ssh_command(
    *,
    target: str,
    key_path: str,
    name: str,
    command: str,
    timeout: int = 60,
) -> RemoteCommandResult:
    if not target:
        return RemoteCommandResult(name=name, ok=False, stdout="", stderr="SSH target not configured.")
    if key_path and not Path(key_path).exists():
        return RemoteCommandResult(name=name, ok=False, stdout="", stderr=f"SSH key not found: {key_path}")

    ssh_command = [
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "IdentitiesOnly=yes",
    ]
    if key_path:
        ssh_command.extend(["-i", key_path])
    ssh_command.extend([target, command])

    completed = subprocess.run(
        ssh_command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return RemoteCommandResult(
        name=name,
        ok=completed.returncode == 0,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def _write_reports(
    *,
    output_dir: Path,
    metadata: dict[str, Any],
    latencies: list[LatencySample],
    remote: list[RemoteCommandResult],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = metadata["timestamp"]
    md_path = output_dir / f"server-runtime-profile-{stamp}.md"
    json_path = output_dir / f"server-runtime-profile-{stamp}.json"

    payload = {
        "metadata": metadata,
        "latencies": [asdict(sample) for sample in latencies],
        "remote": [asdict(item) for item in remote],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"# Server Runtime Profile {stamp}",
        "",
        f"- Base URL: `{metadata['base_url']}`",
        f"- SSH target: `{metadata['ssh_target'] or 'not used'}`",
        f"- Status: `{metadata['status']}`",
        f"- Documents: `{metadata.get('documents_total', 'unknown')}`",
        f"- Qdrant points: `{metadata.get('qdrant_points', 'unknown')}`",
        "",
        "## API Latency",
        "",
    ]
    for sample in latencies:
        lines.append(
            f"- `{sample.name}`: avg `{sample.avg_ms} ms`, p95 `{sample.p95_ms} ms`, "
            f"min `{sample.min_ms} ms`, max `{sample.max_ms} ms`, runs `{sample.runs}`"
        )

    lines.extend(["", "## Server Snapshot", ""])
    for item in remote:
        status = "PASS" if item.ok else "WARN"
        output = item.stdout or item.stderr or "no output"
        lines.extend(
            [
                f"### {status} {item.name}",
                "",
                "```text",
                output[:4000],
                "```",
                "",
            ]
        )

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, json_path


def main() -> int:
    default_key = str(Path.home() / ".ssh" / "local-ai-os-server")
    parser = argparse.ArgumentParser(description="Profile Local AI OS API latency and optional server resource state.")
    parser.add_argument("--base-url", default=os.getenv("LOCAL_AI_OS_BASE_URL", "http://192.168.1.105:8000"))
    parser.add_argument("--username", default=os.getenv("LOCAL_AI_OS_USERNAME", "Admin"))
    parser.add_argument("--password", default=os.getenv("LOCAL_AI_OS_PASSWORD", "password"))
    parser.add_argument("--ssh-target", default=os.getenv("LOCAL_AI_OS_SSH_TARGET", "ai@192.168.1.105"))
    parser.add_argument("--ssh-key", default=os.getenv("LOCAL_AI_OS_SSH_KEY", default_key))
    parser.add_argument("--skip-ssh", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    _login(session, args.base_url, args.username, args.password)

    status_payload = _request_json(session, "GET", f"{args.base_url}/status", timeout=60)
    metadata = {
        "timestamp": _stamp(),
        "base_url": args.base_url,
        "ssh_target": "" if args.skip_ssh else args.ssh_target,
        "status": status_payload.get("status", "unknown"),
        "documents_total": (status_payload.get("storage") or {}).get("documents_total"),
        "qdrant_points": (status_payload.get("qdrant") or {}).get("indexed_point_count"),
    }

    latencies = [
        _measure("health", 10, lambda: _request_json(session, "GET", f"{args.base_url}/health", timeout=30)),
        _measure("status", 5, lambda: _request_json(session, "GET", f"{args.base_url}/status", timeout=60)),
        _measure(
            "documents_list",
            5,
            lambda: _request_json(
                session,
                "GET",
                f"{args.base_url}/documents",
                params={"limit": 50, "offset": 0},
                timeout=60,
            ),
        ),
        _measure(
            "short_chat",
            3,
            lambda: _request_json(
                session,
                "POST",
                f"{args.base_url}/chat",
                json={
                    "message": "Answer in one short sentence: what is Local AI OS?",
                    "persist_conversation": False,
                },
                timeout=180,
            ),
        ),
    ]

    remote: list[RemoteCommandResult] = []
    if not args.skip_ssh:
        commands = {
            "uptime": "uptime",
            "memory": "free -m",
            "disk": "df -h / /home 2>/dev/null || df -h",
            "docker_ps": "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}'",
            "docker_stats": "docker stats --no-stream --format 'table {{.Name}}\\t{{.CPUPerc}}\\t{{.MemUsage}}\\t{{.NetIO}}\\t{{.BlockIO}}'",
        }
        for name, command in commands.items():
            remote.append(
                _run_ssh_command(
                    target=args.ssh_target,
                    key_path=args.ssh_key,
                    name=name,
                    command=command,
                    timeout=90,
                )
            )

    md_path, json_path = _write_reports(
        output_dir=args.output_dir,
        metadata=metadata,
        latencies=latencies,
        remote=remote,
    )
    print(f"Markdown report: {md_path}")
    print(f"JSON report: {json_path}")
    print(json.dumps({"status": metadata["status"], "latency_checks": len(latencies)}, indent=2))
    return 0 if metadata["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
