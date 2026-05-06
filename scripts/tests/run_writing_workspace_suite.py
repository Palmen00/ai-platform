from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "temp" / "writing-workspace"


@dataclass
class WritingResult:
    key: str
    ok: bool
    detail: str
    prompt: str
    reply: str
    source_names: list[str]


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _request(session: requests.Session, method: str, url: str, **kwargs: Any) -> Any:
    response = session.request(method, url, timeout=120, **kwargs)
    response.raise_for_status()
    return response.json() if response.content else {}


def _login(session: requests.Session, base_url: str, username: str, password: str) -> None:
    _request(
        session,
        "POST",
        f"{base_url}/auth/login",
        json={"username": username, "password": password, "remember_me": True},
    )


def _find_document(session: requests.Session, base_url: str, query: str) -> dict[str, Any]:
    payload = _request(
        session,
        "GET",
        f"{base_url}/documents",
        params={"query": query, "limit": 25, "sort_order": "newest"},
    )
    documents = payload.get("documents") or []
    processed = [
        doc
        for doc in documents
        if doc.get("processing_status") == "processed"
        and doc.get("indexing_status") == "indexed"
    ]
    if not processed:
        raise RuntimeError(f"No processed and indexed document found for query: {query}")
    exact = [
        doc
        for doc in processed
        if _normalize(doc.get("original_name") or "") == _normalize(query)
    ]
    return (exact or processed)[0]


def _weak_refusal(reply: str) -> bool:
    weak_patterns = [
        r"\bi cannot create\b",
        r"\bi can'?t create\b",
        r"\bcannot create an action plan\b",
        r"\bcannot write the requested\b",
        r"\bnot enough information to create\b",
    ]
    return any(re.search(pattern, reply, flags=re.IGNORECASE) for pattern in weak_patterns)


def _has_any(reply: str, terms: list[str]) -> bool:
    lowered = reply.lower()
    return any(term.lower() in lowered for term in terms)


def _has_all(reply: str, terms: list[str]) -> bool:
    lowered = reply.lower()
    return all(term.lower() in lowered for term in terms)


def _shape_ok(key: str, reply: str) -> bool:
    if key == "customer_email":
        return _has_any(reply, ["subject:", "subject -"]) and _has_any(
            reply, ["dear", "hello", "hi", "best regards", "kind regards"]
        )
    if key == "incident_report":
        return _has_all(reply, ["executive summary", "timeline", "impact"]) and _has_any(
            reply, ["recommended next", "next steps", "actions taken"]
        )
    if key == "management_summary":
        return _has_any(reply, ["conclusion", "important", "summary"]) and _has_any(
            reply, ["risk", "cost", "decision", "next action"]
        )
    if key == "action_plan":
        return _has_all(reply, ["task", "owner", "deadline"]) and _has_any(
            reply, ["evidence", "source", "unknown"]
        )
    return False


def _run_chat(
    session: requests.Session,
    base_url: str,
    *,
    prompt: str,
    document_id: str,
) -> dict[str, Any]:
    return _request(
        session,
        "POST",
        f"{base_url}/chat",
        json={
            "message": prompt,
            "document_ids": [document_id],
            "persist_conversation": False,
        },
    )


def run_suite(args: argparse.Namespace) -> tuple[list[WritingResult], dict[str, Any]]:
    session = requests.Session()
    _login(session, args.base_url, args.username, args.password)
    document = _find_document(session, args.base_url, args.document_query)

    prompts = {
        "customer_email": (
            "Write a customer email based only on this document. Include a subject,"
            " short explanation, what we know, what we still need, and a professional close."
        ),
        "incident_report": (
            "Write an incident report based only on the uploaded document. Use headings:"
            " Executive summary, Timeline, Impact, Root cause or likely cause,"
            " Actions taken, Open risks, Recommended next steps, Missing information."
        ),
        "management_summary": (
            "Write a management summary from this document. Include the most important"
            " conclusion, key facts, risks/costs, decisions needed, and recommended next actions."
        ),
        "action_plan": (
            "Create an action plan from this document. Use a table with task, owner,"
            " deadline, priority, and evidence. If a value is missing, write Unknown."
        ),
    }

    results: list[WritingResult] = []
    for key, prompt in prompts.items():
        response = _run_chat(
            session,
            args.base_url,
            prompt=prompt,
            document_id=document["id"],
        )
        reply = response.get("reply") or ""
        sources = [
            source.get("document_name") or ""
            for source in (response.get("sources") or [])
        ]
        grounded = bool(sources)
        shape = _shape_ok(key, reply)
        weak = _weak_refusal(reply)
        ok = grounded and shape and not weak
        results.append(
            WritingResult(
                key=key,
                ok=ok,
                detail=f"grounded={grounded}, shape={shape}, weak={weak}, sources={sources}",
                prompt=prompt,
                reply=reply,
                source_names=sources,
            )
        )

    metadata = {
        "base_url": args.base_url,
        "document": document.get("original_name"),
        "document_id": document.get("id"),
    }
    return results, metadata


def write_report(
    *,
    results: list[WritingResult],
    metadata: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _stamp()
    passed = sum(1 for result in results if result.ok)
    total = len(results)
    payload = {
        "timestamp": timestamp,
        **metadata,
        "passed": passed,
        "total": total,
        "results": [asdict(result) for result in results],
    }

    json_path = output_dir / f"writing-workspace-{timestamp}.json"
    md_path = output_dir / f"writing-workspace-{timestamp}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"# Writing Workspace Live Test {timestamp}",
        "",
        f"- Base URL: `{metadata['base_url']}`",
        f"- Scoped document: `{metadata['document']}`",
        f"- Passed: `{passed}/{total}`",
        "",
    ]
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        preview = " ".join(result.reply.split())[:800]
        lines.extend(
            [
                f"- `{status}` {result.key}: {result.detail}",
                f"  Sources: {', '.join(result.source_names) or 'none'}",
                f"  Reply preview: {preview}",
            ]
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, json_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run live writing workspace checks.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default="Admin")
    parser.add_argument("--password", default="password")
    parser.add_argument("--document-query", default="scan-pdf")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        results, metadata = run_suite(args)
        md_path, json_path = write_report(
            results=results,
            metadata=metadata,
            output_dir=args.output_dir,
        )
    except Exception as exc:
        print(f"Writing workspace suite failed: {exc}", file=sys.stderr)
        return 1

    passed = sum(1 for result in results if result.ok)
    total = len(results)
    print(f"Writing workspace suite: {passed}/{total} passed")
    print(f"Markdown report: {md_path}")
    print(f"JSON report: {json_path}")
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        print(f"- {status} {result.key}: {result.detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
