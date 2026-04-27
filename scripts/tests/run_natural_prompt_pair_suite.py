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
DEFAULT_SHEET = ROOT / "backend" / "evals" / "natural_prompt_pair_cases.json"
DEFAULT_OUTPUT_DIR = ROOT / "temp" / "natural-prompt-pairs"

FALLBACK_PHRASES = (
    "i do not have access",
    "i don't have access",
    "i cannot access",
    "i can't access",
    "i do not have enough context",
    "i don't have enough context",
    "i don't have any information",
    "i do not have any information",
    "i'm not aware of any specific",
    "i am not aware of any specific",
    "not in the current context",
    "cannot tell",
    "can't tell",
    "could not find",
    "i could not find",
    "no documents",
    "as an ai",
    "provided for reference. however",
    "there is no mention of a document similar",
    "unfortunately, no specific",
)


@dataclass
class MaterializedCase:
    id: str
    category: str
    situation: str
    selector: str
    perfect_prompt: str
    human_prompt: str
    setup_prompt: str | None
    target_document_id: str | None
    target_document_name: str | None
    other_document_id: str | None
    other_document_name: str | None
    topic: str | None
    requires_sources: bool
    requires_target_name: bool
    min_source_overlap: float
    expected_reply_terms: list[str]
    forbidden_reply_terms: list[str]


@dataclass
class PromptRun:
    prompt: str
    ok: bool
    latency_ms: float
    reply: str
    source_names: list[str]
    retrieval: dict[str, Any] | None
    detail: str


@dataclass
class PairResult:
    case_id: str
    category: str
    situation: str
    selector: str
    target_document_name: str | None
    other_document_name: str | None
    topic: str | None
    perfect: PromptRun
    human: PromptRun
    source_overlap: float
    ok: bool
    detail: str


class SuiteFailure(RuntimeError):
    pass


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _ensure_ok(response: requests.Response, context: str) -> dict[str, Any]:
    if not response.ok:
        raise SuiteFailure(f"{context} failed: {response.status_code} {response.text[:500]}")
    if not response.content:
        return {}
    return response.json()


def _maybe_login(
    session: requests.Session,
    base_url: str,
    username: str,
    password: str,
) -> None:
    auth_status = _ensure_ok(
        session.get(f"{base_url}/auth/status", timeout=30),
        "auth status",
    )
    if not auth_status.get("auth_enabled"):
        return
    if auth_status.get("authenticated"):
        return

    _ensure_ok(
        session.post(
            f"{base_url}/auth/login",
            json={"username": username, "password": password},
            timeout=30,
        ),
        "login",
    )


def _fetch_documents(session: requests.Session, base_url: str) -> list[dict[str, Any]]:
    payload = _ensure_ok(
        session.get(
            f"{base_url}/documents",
            params={"limit": 500, "offset": 0, "sort_order": "newest"},
            timeout=60,
        ),
        "documents",
    )
    documents = list(payload.get("documents", []))
    return [
        document
        for document in documents
        if document.get("processing_status") == "processed"
        and document.get("indexing_status") == "indexed"
    ]


def _fetch_preview_text(
    session: requests.Session,
    base_url: str,
    document_id: str,
) -> str:
    payload = _ensure_ok(
        session.get(f"{base_url}/documents/{document_id}/preview", timeout=60),
        f"preview:{document_id}",
    )
    preview = dict(payload.get("preview", {}))
    text = str(preview.get("extracted_text", "") or "")
    if text.strip():
        return _normalize_text(text)
    chunks = preview.get("chunks", [])
    return _normalize_text(" ".join(str(chunk.get("content", "")) for chunk in chunks))


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").replace("\n", " ").split())


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _short_name(document_name: str) -> str:
    stem = re.sub(r"\.[A-Za-z0-9]{1,8}$", "", document_name)
    stem = re.sub(r"^\d{8}-\d{6}-", "", stem)
    stem = stem.replace("_", " ").replace("-", " ")
    return " ".join(stem.split())[:80] or document_name


def _document_score(document: dict[str, Any]) -> int:
    score = int(document.get("chunk_count") or 0)
    score += min(int(document.get("character_count") or 0) // 500, 20)
    if document.get("document_topics"):
        score += 8
    if document.get("document_summary_anchor"):
        score += 5
    if document.get("similar_documents"):
        score += 5
    if document.get("document_family_key"):
        score += 3
    return score


def _pick_representative_document(documents: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(documents, key=_document_score, reverse=True)[0]


def _pick_topic_document(documents: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    for document in sorted(documents, key=_document_score, reverse=True):
        topics = [str(topic).strip() for topic in document.get("document_topics", []) if str(topic).strip()]
        if topics:
            return document, topics[0]
        entities = [
            str(entity).strip()
            for entity in document.get("document_entities", [])
            if str(entity).strip()
        ]
        if entities:
            return document, entities[0]
        anchor = str(document.get("document_summary_anchor") or "").strip()
        if anchor:
            return document, anchor
    fallback = _pick_representative_document(documents)
    return fallback, _short_name(str(fallback.get("original_name", "")))


def _document_search_text(document: dict[str, Any]) -> str:
    values: list[str] = [
        str(document.get("original_name", "")),
        str(document.get("document_title", "")),
        str(document.get("detected_document_type", "")),
        str(document.get("source_kind", "")),
        str(document.get("document_summary_anchor", "")),
    ]
    values.extend(str(topic) for topic in document.get("document_topics", []) or [])
    values.extend(str(entity) for entity in document.get("document_entities", []) or [])
    return " ".join(values).lower()


def _pick_document_by_hints(
    documents: list[dict[str, Any]],
    hints: list[str],
) -> dict[str, Any] | None:
    normalized_hints = [hint.lower() for hint in hints if hint.strip()]
    if not normalized_hints:
        return None

    candidates: list[tuple[int, dict[str, Any]]] = []
    for document in documents:
        search_text = _document_search_text(document)
        matched = sum(1 for hint in normalized_hints if hint in search_text)
        if matched:
            candidates.append((_document_score(document) + (matched * 20), document))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _pick_ocr_document(documents: list[dict[str, Any]]) -> dict[str, Any] | None:
    ocr_documents = [document for document in documents if document.get("ocr_used")]
    if not ocr_documents:
        return None
    return sorted(ocr_documents, key=_document_score, reverse=True)[0]


def _pick_similar_document(documents: list[dict[str, Any]]) -> dict[str, Any] | None:
    for document in sorted(documents, key=_document_score, reverse=True):
        if document.get("similar_documents"):
            return document

    family_counts: dict[str, int] = {}
    for document in documents:
        family_key = str(document.get("document_family_key") or "")
        if family_key:
            family_counts[family_key] = family_counts.get(family_key, 0) + 1
    for document in sorted(documents, key=_document_score, reverse=True):
        family_key = str(document.get("document_family_key") or "")
        if family_key and family_counts.get(family_key, 0) > 1:
            return document
    return None


def _pick_document_pair(
    documents: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    by_id = {str(document.get("id")): document for document in documents}
    for document in sorted(documents, key=_document_score, reverse=True):
        for match in document.get("similar_documents", []) or []:
            other = by_id.get(str(match.get("document_id")))
            if other:
                return document, other

    families: dict[str, list[dict[str, Any]]] = {}
    for document in documents:
        family_key = str(document.get("document_family_key") or "")
        if family_key:
            families.setdefault(family_key, []).append(document)
    for family_documents in families.values():
        if len(family_documents) >= 2:
            ordered = sorted(family_documents, key=_document_score, reverse=True)
            return ordered[0], ordered[1]

    if len(documents) >= 2:
        ordered = sorted(documents, key=_document_score, reverse=True)
        return ordered[0], ordered[1]
    return None


def _format_prompt(template: str, values: dict[str, str]) -> str:
    return template.format(**values)


def _materialize_case(
    raw_case: dict[str, Any],
    documents: list[dict[str, Any]],
) -> MaterializedCase | None:
    selector = str(raw_case["selector"])
    target: dict[str, Any] | None = None
    other: dict[str, Any] | None = None
    topic: str | None = None

    if selector in {"latest_document", "representative_document"}:
        target = documents[0] if selector == "latest_document" else _pick_representative_document(documents)
    elif selector == "runtime":
        target = None
    elif selector == "topic_document":
        target, topic = _pick_topic_document(documents)
    elif selector == "typed_document":
        target = _pick_document_by_hints(
            documents,
            [str(value) for value in raw_case.get("type_hints", [])],
        )
        if target is None:
            return None
    elif selector == "ocr_document":
        target = _pick_ocr_document(documents)
        if target is None:
            return None
    elif selector == "similar_document":
        target = _pick_similar_document(documents)
        if target is None:
            return None
    elif selector == "document_pair":
        pair = _pick_document_pair(documents)
        if pair is None:
            return None
        target, other = pair
    elif selector == "inventory":
        target = None
    else:
        raise SuiteFailure(f"Unsupported selector: {selector}")

    target_name = str(target.get("original_name", "")) if target else ""
    other_name = str(other.get("original_name", "")) if other else ""
    values = {
        "document_name": target_name,
        "short_name": _short_name(target_name),
        "other_document_name": other_name,
        "other_short_name": _short_name(other_name),
        "document_type": str(target.get("detected_document_type") or target.get("source_kind") or "document") if target else "document",
        "topic": topic or "",
    }

    return MaterializedCase(
        id=str(raw_case["id"]),
        category=str(raw_case.get("category") or "General"),
        situation=str(raw_case.get("situation") or ""),
        selector=selector,
        perfect_prompt=_format_prompt(str(raw_case["perfect_prompt"]), values),
        human_prompt=_format_prompt(str(raw_case["human_prompt"]), values),
        setup_prompt=(
            _format_prompt(str(raw_case["setup_prompt"]), values)
            if raw_case.get("setup_prompt")
            else None
        ),
        target_document_id=str(target.get("id")) if target else None,
        target_document_name=target_name or None,
        other_document_id=str(other.get("id")) if other else None,
        other_document_name=other_name or None,
        topic=topic,
        requires_sources=bool(raw_case.get("requires_sources", False)),
        requires_target_name=bool(raw_case.get("requires_target_name", False)),
        min_source_overlap=float(raw_case.get("min_source_overlap", 0.0)),
        expected_reply_terms=[
            _format_prompt(str(term), values)
            for term in raw_case.get("expected_reply_terms", [])
        ],
        forbidden_reply_terms=[
            _format_prompt(str(term), values)
            for term in raw_case.get("forbidden_reply_terms", [])
        ],
    )


def _materialize_cases(
    sheet: dict[str, Any],
    documents: list[dict[str, Any]],
    max_cases: int,
) -> list[MaterializedCase]:
    if not documents:
        raise SuiteFailure("No processed and indexed documents were available for prompt-pair testing.")

    cases: list[MaterializedCase] = []
    for raw_case in sheet.get("cases", []):
        materialized = _materialize_case(dict(raw_case), documents)
        if materialized:
            cases.append(materialized)
        if max_cases > 0 and len(cases) >= max_cases:
            break
    return cases


def _ask(
    session: requests.Session,
    base_url: str,
    *,
    prompt: str,
    model: str | None,
    history: list[dict[str, Any]] | None = None,
) -> tuple[float, dict[str, Any]]:
    body: dict[str, Any] = {
        "message": prompt,
        "history": history or [],
        "document_ids": [],
        "persist_conversation": False,
    }
    if model:
        body["model"] = model

    started = time.perf_counter()
    response = session.post(f"{base_url}/chat", json=body, timeout=300)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return elapsed_ms, _ensure_ok(response, f"chat:{prompt[:80]}")


def _source_names(payload: dict[str, Any]) -> list[str]:
    return [
        str(source.get("document_name"))
        for source in payload.get("sources", []) or []
        if source.get("document_name")
    ]


def _has_fallback(reply: str) -> bool:
    lowered = reply.lower()
    for phrase in FALLBACK_PHRASES:
        if phrase == "as an ai":
            if re.search(r"\bas an ai(?!-)\b", lowered):
                return True
            continue
        if phrase in lowered:
            return True
    return False


def _contains_expected_terms(reply: str, terms: list[str]) -> bool:
    if not terms:
        return True
    normalized_reply = _normalize_name(reply)
    return all(_normalize_name(term) in normalized_reply for term in terms if term.strip())


def _avoids_forbidden_terms(reply: str, terms: list[str]) -> bool:
    if not terms:
        return True
    normalized_reply = _normalize_name(reply)
    return not any(_normalize_name(term) in normalized_reply for term in terms if term.strip())


def _target_mentioned(case: MaterializedCase, reply: str, source_names: list[str]) -> bool:
    if not case.target_document_name:
        return True
    target = _normalize_name(case.target_document_name)
    normalized_reply = _normalize_name(reply)
    normalized_sources = [_normalize_name(source_name) for source_name in source_names]
    return target in normalized_reply or any(target in source for source in normalized_sources)


def _source_overlap(left: list[str], right: list[str]) -> float:
    left_set = {_normalize_name(name) for name in left if name}
    right_set = {_normalize_name(name) for name in right if name}
    if not left_set and not right_set:
        return 1.0
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / max(len(left_set), 1)


def _evaluate_run(
    case: MaterializedCase,
    payload: dict[str, Any],
    latency_ms: float,
    prompt: str,
    *,
    compare_sources: list[str] | None = None,
) -> PromptRun:
    reply = str(payload.get("reply", "") or "").strip()
    sources = _source_names(payload)
    retrieval = payload.get("retrieval")

    reply_ok = len(reply) >= 12 and not _has_fallback(reply)
    source_ok = True
    if case.requires_sources:
        source_ok = len(sources) > 0
    target_ok = True
    if case.requires_target_name:
        target_ok = _target_mentioned(case, reply, sources)

    overlap_ok = True
    if compare_sources is not None and compare_sources and case.min_source_overlap > 0:
        overlap_ok = _source_overlap(compare_sources, sources) >= case.min_source_overlap
    expected_ok = _contains_expected_terms(reply, case.expected_reply_terms)
    forbidden_ok = _avoids_forbidden_terms(reply, case.forbidden_reply_terms)

    ok = reply_ok and source_ok and target_ok and overlap_ok and expected_ok and forbidden_ok
    details = [
        "reply-ok" if reply_ok else "reply-weak-or-fallback",
        "sources-ok" if source_ok else "missing-sources",
        "target-ok" if target_ok else "target-not-mentioned",
        "overlap-ok" if overlap_ok else "source-overlap-low",
        "expected-ok" if expected_ok else "expected-terms-missing",
        "forbidden-ok" if forbidden_ok else "forbidden-terms-found",
    ]
    return PromptRun(
        prompt=prompt,
        ok=ok,
        latency_ms=latency_ms,
        reply=reply,
        source_names=sources,
        retrieval=retrieval if isinstance(retrieval, dict) else None,
        detail=", ".join(details),
    )


def _run_case(
    session: requests.Session,
    base_url: str,
    model: str | None,
    case: MaterializedCase,
) -> PairResult:
    perfect_latency, perfect_payload = _ask(
        session,
        base_url,
        prompt=case.perfect_prompt,
        model=model,
    )
    perfect = _evaluate_run(
        case,
        perfect_payload,
        perfect_latency,
        case.perfect_prompt,
    )

    human_history: list[dict[str, Any]] = []
    if case.setup_prompt:
        _, setup_payload = _ask(
            session,
            base_url,
            prompt=case.setup_prompt,
            model=model,
        )
        setup_reply = str(setup_payload.get("reply", "") or "").strip()
        human_history = [
            {"role": "user", "content": case.setup_prompt},
            {
                "role": "assistant",
                "content": setup_reply,
                "model": setup_payload.get("model"),
                "sources": setup_payload.get("sources", []),
                "retrieval": setup_payload.get("retrieval"),
            },
        ]

    human_latency, human_payload = _ask(
        session,
        base_url,
        prompt=case.human_prompt,
        model=model,
        history=human_history,
    )
    human = _evaluate_run(
        case,
        human_payload,
        human_latency,
        case.human_prompt,
        compare_sources=perfect.source_names,
    )

    overlap = _source_overlap(perfect.source_names, human.source_names)
    ok = perfect.ok and human.ok
    detail = "passed" if ok else "failed"
    if case.min_source_overlap > 0:
        detail = f"{detail}, source-overlap={overlap:.2f}"

    return PairResult(
        case_id=case.id,
        category=case.category,
        situation=case.situation,
        selector=case.selector,
        target_document_name=case.target_document_name,
        other_document_name=case.other_document_name,
        topic=case.topic,
        perfect=perfect,
        human=human,
        source_overlap=overlap,
        ok=ok,
        detail=detail,
    )


def _write_markdown(
    path: Path,
    metadata: dict[str, Any],
    cases: list[MaterializedCase],
    results: list[PairResult],
) -> None:
    passed = sum(1 for result in results if result.ok)
    lines = [
        "# Natural Prompt Pair QA Report",
        "",
        f"- Timestamp: `{metadata['timestamp']}`",
        f"- Base URL: `{metadata['base_url']}`",
        f"- Model: `{metadata['model'] or 'backend default'}`",
        f"- Cases: `{passed}/{len(results)}` passed",
        "",
        "## Category Summary",
        "",
        "| Category | Passed | Total |",
        "| --- | ---: | ---: |",
    ]

    categories = sorted({case.category for case in cases})
    for category in categories:
        category_results = [result for result in results if result.category == category]
        category_passed = sum(1 for result in category_results if result.ok)
        lines.append(f"| {category} | {category_passed} | {len(category_results)} |")

    lines.extend([
        "",
        "## Question Sheet",
        "",
        "| Category | Situation | Case | Target | Perfect prompt | Human prompt |",
        "| --- | --- | --- | --- | --- | --- |",
    ])

    for case in cases:
        target_parts = [
            value
            for value in (case.target_document_name, case.other_document_name, case.topic)
            if value
        ]
        target = "<br>".join(target_parts) if target_parts else "inventory"
        lines.append(
            "| "
            + " | ".join(
                [
                    case.category.replace("|", "\\|"),
                    case.situation.replace("|", "\\|"),
                    f"`{case.id}`",
                    target.replace("|", "\\|"),
                    case.perfect_prompt.replace("|", "\\|"),
                    case.human_prompt.replace("|", "\\|"),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Results", ""])
    for category in categories:
        lines.extend([f"### {category}", ""])
        for result in [item for item in results if item.category == category]:
            status = "PASS" if result.ok else "FAIL"
            lines.extend(
                [
                    f"#### {result.case_id} - {status}",
                    "",
                    f"- Situation: `{result.situation or 'n/a'}`",
                    f"- Target: `{result.target_document_name or 'n/a'}`",
                    f"- Other: `{result.other_document_name or 'n/a'}`",
                    f"- Topic: `{result.topic or 'n/a'}`",
                    f"- Source overlap: `{result.source_overlap:.2f}`",
                    f"- Perfect detail: `{result.perfect.detail}`",
                    f"- Human detail: `{result.human.detail}`",
                    f"- Perfect latency: `{result.perfect.latency_ms:.1f} ms`",
                    f"- Human latency: `{result.human.latency_ms:.1f} ms`",
                    f"- Perfect sources: `{', '.join(result.perfect.source_names) or 'none'}`",
                    f"- Human sources: `{', '.join(result.human.source_names) or 'none'}`",
                    "",
                    "**Perfect reply**",
                    "",
                    result.perfect.reply or "_empty_",
                    "",
                    "**Human reply**",
                    "",
                    result.human.reply or "_empty_",
                    "",
                ]
            )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run paired perfect-vs-human prompt QA against the live chat API."
    )
    parser.add_argument("--base-url", default="http://192.168.1.105:8000")
    parser.add_argument("--username", default="Admin")
    parser.add_argument("--password", default="password")
    parser.add_argument("--model", default="")
    parser.add_argument("--sheet", type=Path, default=DEFAULT_SHEET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-cases", type=int, default=0)
    args = parser.parse_args()

    sheet = json.loads(args.sheet.read_text(encoding="utf-8"))
    args.output_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    _maybe_login(session, args.base_url, args.username, args.password)

    documents = _fetch_documents(session, args.base_url)
    cases = _materialize_cases(sheet, documents, args.max_cases)
    if not cases:
        raise SuiteFailure("No prompt-pair cases could be materialized from the current documents.")

    model = args.model.strip() or None
    results = [_run_case(session, args.base_url, model, case) for case in cases]

    stamp = _stamp()
    report_md = args.output_dir / f"natural-prompt-pairs-{stamp}.md"
    report_json = args.output_dir / f"natural-prompt-pairs-{stamp}.json"
    metadata = {
        "timestamp": stamp,
        "base_url": args.base_url,
        "model": model,
        "sheet": str(args.sheet),
        "document_count": len(documents),
        "passed_cases": sum(1 for result in results if result.ok),
        "total_cases": len(results),
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
    _write_markdown(report_md, metadata, cases, results)

    print(f"Markdown report: {report_md}")
    print(f"JSON report: {report_json}")
    print(
        json.dumps(
            {
                "passed_cases": metadata["passed_cases"],
                "total_cases": metadata["total_cases"],
                "failed_cases": [
                    result.case_id for result in results if not result.ok
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0 if metadata["passed_cases"] == metadata["total_cases"] else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Natural prompt pair suite failed: {exc}", file=sys.stderr)
        sys.exit(1)
