from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "temp" / "vector-rag-scale"

TOPICS = (
    "finance reconciliation",
    "support operations",
    "security review",
    "infrastructure runtime",
    "customer incident",
    "product catalogue",
    "compliance policy",
    "warehouse logistics",
    "developer runbook",
    "sales analytics",
)

ENTITIES = (
    "Aurora Retail",
    "Northwind Manufacturing",
    "Fabrikam Medical",
    "Solstice Logistics",
    "BlueHarbor Support",
    "Contoso Field Ops",
    "Meridian Foods",
    "Fjordbyte Systems",
)


@dataclass(frozen=True)
class TargetDoc:
    index: int
    filename: str
    key: str
    topic: str
    entity: str
    phrase: str


@dataclass(frozen=True)
class ScaleCase:
    key: str
    prompt: str
    expected_terms: tuple[str, ...] = ()
    expected_any_terms: tuple[str, ...] = ()
    expected_source_fragments: tuple[str, ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    document_ids: tuple[str, ...] = ()
    require_no_sources: bool = False
    require_sources: bool = True
    min_semantic_candidates: int = 0
    max_latency_ms: float | None = None


@dataclass
class ScaleResult:
    key: str
    ok: bool
    detail: str
    latency_ms: float
    prompt: str
    reply: str
    source_names: list[str]
    retrieval: dict[str, Any] | None
    expected_terms: list[str]
    expected_source_fragments: list[str]


class SuiteFailure(RuntimeError):
    pass


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _contains_all(reply: str, terms: tuple[str, ...]) -> bool:
    normalized_reply = _normalize(reply)
    compact_reply = re.sub(r"[^a-z0-9]+", "", normalized_reply)
    for term in terms:
        normalized_term = _normalize(term)
        compact_term = re.sub(r"[^a-z0-9]+", "", normalized_term)
        if normalized_term in normalized_reply:
            continue
        if compact_term and compact_term in compact_reply:
            continue
        return False
    return True


def _source_match(source_names: list[str], fragments: tuple[str, ...]) -> bool:
    normalized_sources = [source.lower() for source in source_names]
    return all(
        any(fragment.lower() in source for source in normalized_sources)
        for fragment in fragments
    )


def _ensure_ok(response: requests.Response, context: str) -> dict[str, Any]:
    if not response.ok:
        raise SuiteFailure(f"{context} failed: {response.status_code} {response.text[:700]}")
    if not response.content:
        return {}
    return response.json()


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout: int = 120,
    **kwargs: Any,
) -> dict[str, Any]:
    return _ensure_ok(session.request(method, url, timeout=timeout, **kwargs), f"{method} {url}")


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


def _target_indexes(document_count: int) -> tuple[int, int, int]:
    if document_count < 3:
        raise SuiteFailure("Vector RAG scale suite requires at least 3 documents.")

    preferred = (
        min(max(17, document_count // 20), document_count - 1),
        min(max(118, document_count // 3), document_count - 1),
        min(max(731, (document_count * 3) // 4), document_count - 1),
    )
    fallback = (
        max(0, document_count // 4),
        max(1, document_count // 2),
        max(2, (document_count * 3) // 4),
        document_count - 1,
        0,
    )
    targets: list[int] = []
    for candidate in preferred + fallback:
        bounded = min(max(candidate, 0), document_count - 1)
        if bounded not in targets:
            targets.append(bounded)
        if len(targets) == 3:
            return (targets[0], targets[1], targets[2])

    raise SuiteFailure("Could not choose three distinct target documents.")


def _build_document_text(run_id: str, index: int, special_phrase: str | None = None) -> str:
    topic = TOPICS[index % len(TOPICS)]
    entity = ENTITIES[index % len(ENTITIES)]
    key = f"{run_id.upper()}-KEY-{index:04d}"
    phrase = special_phrase or (
        f"{topic} notes for {entity} with routine operating facts and low priority follow-up"
    )
    return (
        f"# Vector RAG Scale Document {index:04d}\n\n"
        f"Run ID: {run_id}\n"
        f"Unique retrieval key: {key}\n"
        f"Topic family: {topic}\n"
        f"Primary entity: {entity}\n"
        f"Semantic description: {phrase}.\n"
        f"Metric snapshot: latency_ms={120 + (index % 80)}, error_count={index % 7}, "
        f"storage_bucket=scale-bucket-{index % 13}.\n"
        "Operational note: this synthetic file is only used for retrieval scale validation.\n"
    )


def _build_fixtures(base_dir: Path, run_id: str, document_count: int) -> dict[int, Path]:
    base_dir.mkdir(parents=True, exist_ok=True)
    special_phrases = {
        _target_indexes(document_count)[0]: (
            "an espresso maintenance plan for orbital research stations; "
            "also described as maintaining coffee equipment in space labs"
        ),
        _target_indexes(document_count)[1]: (
            "battery warranty escalation for electric cargo bicycles; "
            "also described as warranty escalation for electric freight bikes"
        ),
        _target_indexes(document_count)[-1]: (
            "cold chain invoice anomaly for medical supply deliveries; "
            "also described as refrigerated medical shipment billing anomalies"
        ),
    }

    paths: dict[int, Path] = {}
    for index in range(document_count):
        path = base_dir / f"{run_id}-scale-doc-{index:04d}.md"
        path.write_text(
            _build_document_text(run_id, index, special_phrases.get(index)),
            encoding="utf-8",
        )
        paths[index] = path
    return paths


def _upload(session: requests.Session, base_url: str, path: Path) -> dict[str, Any]:
    content_type = mimetypes.guess_type(path.name)[0] or "text/markdown"
    with path.open("rb") as handle:
        response = session.post(
            f"{base_url}/documents/upload",
            files={"file": (path.name, handle, content_type)},
            timeout=120,
        )
    payload = _ensure_ok(response, f"upload:{path.name}")
    return dict(payload.get("document") or {})


def _list_documents(session: requests.Session, base_url: str, query: str) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    offset = 0
    while True:
        payload = _request_json(
            session,
            "GET",
            f"{base_url}/documents",
            params={"limit": 1000, "offset": offset, "query": query, "sort_order": "newest"},
            timeout=90,
        )
        batch = list(payload.get("documents") or [])
        documents.extend(batch)
        if not payload.get("has_more") or not batch:
            return documents
        offset += len(batch)


def _wait_for_documents(
    session: requests.Session,
    base_url: str,
    run_id: str,
    uploaded_ids: list[str],
    *,
    timeout_seconds: int,
) -> dict[str, dict[str, Any]]:
    expected_ids = set(uploaded_ids)
    deadline = time.time() + timeout_seconds
    last_counts = ""
    while time.time() < deadline:
        documents = {
            str(document.get("id")): document
            for document in _list_documents(session, base_url, run_id)
            if str(document.get("id")) in expected_ids
        }
        processed = [
            document
            for document in documents.values()
            if document.get("processing_status") == "processed"
            and document.get("indexing_status") == "indexed"
        ]
        failed = [
            document
            for document in documents.values()
            if document.get("processing_status") == "failed"
            or document.get("indexing_status") == "failed"
        ]
        counts = f"{len(processed)}/{len(expected_ids)} indexed, {len(failed)} failed"
        if counts != last_counts:
            print(f"[WAIT] {counts}")
            last_counts = counts
        if failed:
            failed_names = ", ".join(str(document.get("original_name")) for document in failed[:5])
            raise SuiteFailure(f"Document processing failed: {failed_names}")
        if len(processed) == len(expected_ids):
            return documents
        time.sleep(5)
    raise SuiteFailure(f"Timed out waiting for documents: {last_counts}")


def _ask(
    session: requests.Session,
    base_url: str,
    prompt: str,
    *,
    document_ids: list[str] | None = None,
    model: str | None = None,
) -> tuple[float, dict[str, Any]]:
    started = time.perf_counter()
    payload = _request_json(
        session,
        "POST",
        f"{base_url}/chat",
        json={
            "message": prompt,
            "model": model,
            "history": [],
            "document_ids": document_ids or [],
            "persist_conversation": False,
        },
        timeout=240,
    )
    return (time.perf_counter() - started) * 1000.0, payload


def _build_cases(
    run_id: str,
    documents_by_index: dict[int, dict[str, Any]],
) -> list[ScaleCase]:
    indexes = _target_indexes(max(documents_by_index) + 1)
    first_index = indexes[0]
    second_index = indexes[1]
    third_index = indexes[-1]

    first = documents_by_index[first_index]
    second = documents_by_index[second_index]
    third = documents_by_index[third_index]

    first_name = str(first["original_name"])
    second_name = str(second["original_name"])
    third_name = str(third["original_name"])

    first_id = str(first["id"])
    third_id = str(third["id"])
    corpus_ids = tuple(str(document["id"]) for document in documents_by_index.values())

    first_key = f"{run_id.upper()}-KEY-{first_index:04d}"
    second_key = f"{run_id.upper()}-KEY-{second_index:04d}"
    third_key = f"{run_id.upper()}-KEY-{third_index:04d}"

    return [
        ScaleCase(
            key="selected_document_exact_key",
            prompt="What unique retrieval key and topic family are in this selected document?",
            document_ids=(first_id,),
            expected_terms=(first_key,),
            expected_source_fragments=(first_name,),
            min_semantic_candidates=0,
        ),
        ScaleCase(
            key="unscoped_exact_key_lookup",
            prompt=f"Which document mentions {second_key}, and what is its primary entity?",
            expected_terms=(second_key,),
            expected_source_fragments=(second_name,),
            min_semantic_candidates=0,
        ),
        ScaleCase(
            key="semantic_space_coffee_lookup",
            prompt="Find the file about maintaining coffee equipment in space labs.",
            document_ids=corpus_ids,
            expected_any_terms=(first_key, "espresso", "orbital", first_name),
            expected_source_fragments=(first_name,),
            min_semantic_candidates=1,
        ),
        ScaleCase(
            key="semantic_cargo_bike_warranty_lookup",
            prompt="Which source is about warranty escalation for electric freight bikes?",
            document_ids=corpus_ids,
            expected_any_terms=(second_key, "cargo", "bicycles", second_name),
            expected_source_fragments=(second_name,),
            min_semantic_candidates=1,
        ),
        ScaleCase(
            key="semantic_medical_cold_chain_lookup",
            prompt="Find the document about refrigerated medical shipment billing anomalies.",
            document_ids=corpus_ids,
            expected_any_terms=(third_key, "cold chain", "medical", third_name),
            expected_source_fragments=(third_name,),
            min_semantic_candidates=1,
        ),
        ScaleCase(
            key="selected_document_filter_precision",
            prompt="Ignore other files. What unique retrieval key is in the selected document?",
            document_ids=(third_id,),
            expected_terms=(third_key,),
            expected_source_fragments=(third_name,),
            forbidden_terms=(first_key, second_key),
        ),
        ScaleCase(
            key="missing_scale_fact_uncertainty",
            prompt="What is the Neptune Moose launch authorization code?",
            document_ids=corpus_ids,
            expected_any_terms=(
                "cannot find",
                "not find",
                "missing",
                "hittar inte",
                "not provided",
                "don't have access",
                "do not have access",
                "not available",
                "can't provide",
                "couldn't find",
            ),
            forbidden_terms=("NEPTUNE-MOOSE-42",),
            require_sources=False,
        ),
        ScaleCase(
            key="general_coding_no_rag_noise",
            prompt="Explain Python list comprehension vs generator expression with a tiny code example.",
            expected_any_terms=("list comprehension", "generator"),
            require_sources=False,
            require_no_sources=True,
        ),
    ]


def _evaluate(case: ScaleCase, latency_ms: float, payload: dict[str, Any]) -> ScaleResult:
    reply = str(payload.get("reply") or "")
    sources = list(payload.get("sources") or [])
    source_names = [str(source.get("document_name") or "") for source in sources]
    retrieval = payload.get("retrieval")
    normalized_reply = _normalize(reply)
    semantic_candidates = int((retrieval or {}).get("semantic_candidates") or 0)

    checks = {
        "reply": bool(reply.strip()),
        "expected_terms": _contains_all(reply, case.expected_terms),
        "expected_any_terms": (
            True
            if not case.expected_any_terms
            else any(_normalize(term) in normalized_reply for term in case.expected_any_terms)
        ),
        "sources": (
            len(source_names) == 0
            if case.require_no_sources
            else (not case.require_sources or bool(source_names))
        ),
        "source_fragments": _source_match(source_names, case.expected_source_fragments),
        "forbidden_terms": not any(_normalize(term) in normalized_reply for term in case.forbidden_terms),
        "semantic_candidates": semantic_candidates >= case.min_semantic_candidates,
        "latency": case.max_latency_ms is None or latency_ms <= case.max_latency_ms,
    }
    failed = [name for name, ok in checks.items() if not ok]
    return ScaleResult(
        key=case.key,
        ok=not failed,
        detail="passed" if not failed else "failed checks: " + ", ".join(failed),
        latency_ms=round(latency_ms, 1),
        prompt=case.prompt,
        reply=reply,
        source_names=source_names,
        retrieval=retrieval,
        expected_terms=list(case.expected_terms or case.expected_any_terms),
        expected_source_fragments=list(case.expected_source_fragments),
    )


def _delete_documents(session: requests.Session, base_url: str, document_ids: list[str]) -> None:
    for document_id in document_ids:
        response = session.delete(f"{base_url}/documents/{document_id}", timeout=30)
        if response.status_code in {200, 404}:
            continue
        print(f"[WARN] delete {document_id} failed: {response.status_code} {response.text[:200]}")


def _write_reports(
    output_dir: Path,
    metadata: dict[str, Any],
    results: list[ScaleResult],
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = str(metadata["timestamp"])
    json_path = output_dir / f"vector-rag-scale-{stamp}.json"
    md_path = output_dir / f"vector-rag-scale-{stamp}.md"
    json_path.write_text(
        json.dumps(
            {"metadata": metadata, "results": [asdict(result) for result in results]},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    passed = sum(1 for result in results if result.ok)
    lines = [
        f"# Vector RAG Scale Suite {stamp}",
        "",
        f"- Base URL: `{metadata['base_url']}`",
        f"- Documents uploaded: `{metadata['document_count']}`",
        f"- Upload seconds: `{metadata['upload_seconds']}`",
        f"- Index seconds: `{metadata['index_seconds']}`",
        f"- Passed: `{passed}/{len(results)}`",
        "",
        "## Results",
        "",
    ]
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        lines.extend(
            [
                f"- `{status}` {result.key}: {result.detail}",
                f"  Latency: `{result.latency_ms} ms`",
                f"  Sources: `{', '.join(result.source_names) or 'none'}`",
                f"  Reply: {result.reply[:700]}",
            ]
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path, json_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Upload a synthetic corpus and run vector/RAG scale checks."
    )
    parser.add_argument("--base-url", default=os.getenv("LOCAL_AI_OS_BASE_URL", "http://192.168.1.105:8000"))
    parser.add_argument("--username", default=os.getenv("LOCAL_AI_OS_USERNAME", "Admin"))
    parser.add_argument("--password", default=os.getenv("LOCAL_AI_OS_PASSWORD", "password"))
    parser.add_argument("--model", default=os.getenv("LOCAL_AI_OS_MODEL", ""))
    parser.add_argument("--documents", type=int, default=1000)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--process-timeout", type=int, default=2400)
    parser.add_argument("--upload-pause-every", type=int, default=100)
    parser.add_argument("--upload-pause-seconds", type=float, default=1.0)
    parser.add_argument("--keep-documents", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.documents < 10:
        raise SuiteFailure("--documents must be at least 10 for meaningful scale coverage.")

    timestamp = _stamp()
    run_id = f"vrag-{timestamp}"
    fixture_dir = args.output_dir / f"fixtures-{run_id}"
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})

    uploaded_ids: list[str] = []
    results: list[ScaleResult] = []
    upload_seconds = 0.0
    index_seconds = 0.0

    try:
        _request_json(session, "GET", f"{args.base_url}/health", timeout=30)
        _login(session, args.base_url, args.username, args.password)
        paths = _build_fixtures(fixture_dir, run_id, args.documents)

        upload_started = time.perf_counter()
        uploaded_by_index: dict[int, dict[str, Any]] = {}
        for index, path in paths.items():
            document = _upload(session, args.base_url, path)
            uploaded_ids.append(str(document["id"]))
            uploaded_by_index[index] = document
            if (index + 1) % args.upload_pause_every == 0:
                print(f"[UPLOAD] {index + 1}/{args.documents}")
                time.sleep(args.upload_pause_seconds)
        upload_seconds = round(time.perf_counter() - upload_started, 1)

        index_started = time.perf_counter()
        processed_by_id = _wait_for_documents(
            session,
            args.base_url,
            run_id,
            uploaded_ids,
            timeout_seconds=args.process_timeout,
        )
        index_seconds = round(time.perf_counter() - index_started, 1)

        documents_by_index = {
            index: processed_by_id[str(uploaded_by_index[index]["id"])]
            for index in uploaded_by_index
        }
        cases = _build_cases(run_id, documents_by_index)

        for case in cases:
            latency_ms, payload = _ask(
                session,
                args.base_url,
                case.prompt,
                document_ids=list(case.document_ids),
                model=args.model or None,
            )
            result = _evaluate(case, latency_ms, payload)
            results.append(result)
            print(f"[{'PASS' if result.ok else 'FAIL'}] {case.key}: {result.detail}")

    finally:
        if uploaded_ids and not args.keep_documents:
            print(f"[CLEANUP] deleting {len(uploaded_ids)} uploaded scale documents")
            _delete_documents(session, args.base_url, uploaded_ids)

    metadata = {
        "timestamp": timestamp,
        "run_id": run_id,
        "base_url": args.base_url,
        "model": args.model or "default",
        "document_count": args.documents,
        "upload_seconds": upload_seconds,
        "index_seconds": index_seconds,
        "cleanup": not args.keep_documents,
        "passed": sum(1 for result in results if result.ok),
        "total": len(results),
    }
    md_path, json_path = _write_reports(args.output_dir, metadata, results)
    print(f"Markdown report: {md_path}")
    print(f"JSON report: {json_path}")
    print(json.dumps({"passed": metadata["passed"], "total": metadata["total"]}, indent=2))
    return 0 if metadata["passed"] == metadata["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
