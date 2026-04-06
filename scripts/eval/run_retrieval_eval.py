import argparse
import json
import os
import sys
from pathlib import Path


def load_backend() -> tuple[object, object]:
    repo_root = Path(__file__).resolve().parents[2]
    backend_dir = repo_root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    from app.services.chat_orchestrator import ChatOrchestrator
    from app.services.documents import DocumentService

    return ChatOrchestrator(), DocumentService()


CONFIDENCE_RANK = {
    "low": 0,
    "medium": 1,
    "high": 2,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run retrieval and optional answer evals against the local document set."
    )
    parser.add_argument(
        "--suite",
        default="backend/evals/retrieval_baseline.json",
        help="Path to the eval suite JSON file.",
    )
    parser.add_argument(
        "--with-replies",
        action="store_true",
        help="Also generate model replies and validate reply-level expectations.",
    )
    parser.add_argument(
        "--write-report",
        default="",
        help="Optional path to write a JSON report.",
    )
    return parser.parse_args()


def load_suite(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def document_maps(document_service: object) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
    documents = document_service.list_documents()
    name_to_id = {document.original_name: document.id for document in documents}
    name_to_meta = {
        document.original_name: {
            "id": document.id,
            "processing_status": document.processing_status,
            "indexing_status": document.indexing_status,
        }
        for document in documents
    }
    return name_to_id, name_to_meta


def confidence_at_least(actual: str, minimum: str) -> bool:
    return CONFIDENCE_RANK.get(actual, -1) >= CONFIDENCE_RANK.get(minimum, -1)


def normalize_text(value: str) -> str:
    lowered = value.lower().replace("-", " ")
    return " ".join(lowered.split())


def safe_print(value: str) -> None:
    normalized = value.encode("cp1252", errors="replace").decode("cp1252")
    print(normalized)


def run_case(
    orchestrator: object,
    document_service: object,
    name_to_id: dict[str, str],
    case: dict[str, object],
    with_replies: bool,
) -> dict[str, object]:
    question = str(case["question"])
    scope_names = [str(name) for name in case.get("scope_documents", [])]
    required_documents = [str(name) for name in case.get("required_documents", [])]
    missing_required = [name for name in required_documents if name not in name_to_id]

    if missing_required:
        return {
            "id": case.get("id", question),
            "question": question,
            "scope_documents": scope_names,
            "returned_documents": [],
            "returned_sources": 0,
            "mode": "skipped",
            "confidence": "low",
            "top_source_score": 0.0,
            "checks": [],
            "passed": False,
            "skipped": True,
            "skip_reason": f"missing required documents: {', '.join(missing_required)}",
            "reply": None,
        }

    scope_ids = [name_to_id[name] for name in scope_names if name in name_to_id]

    retrieval_result = orchestrator.retrieval_service.retrieve(
        question,
        limit=4,
        allowed_document_ids=scope_ids,
    )
    sources = retrieval_result.sources
    debug = retrieval_result.debug
    returned_documents = list(dict.fromkeys(source.document_name for source in sources))

    checks: list[dict[str, object]] = []

    expected_documents = [str(name) for name in case.get("expected_documents", [])]
    if expected_documents:
        missing = [name for name in expected_documents if name not in returned_documents]
        checks.append(
            {
                "name": "expected_documents",
                "passed": not missing,
                "detail": "all expected documents returned"
                if not missing
                else f"missing: {', '.join(missing)}",
            }
        )

    allowed_support_documents = [
        str(name) for name in case.get("allowed_support_documents", [])
    ]
    if expected_documents or allowed_support_documents:
        allowed_documents = set(expected_documents + allowed_support_documents)
        unexpected = [
            name for name in returned_documents if name not in allowed_documents
        ]
        checks.append(
            {
                "name": "unexpected_documents",
                "passed": not unexpected,
                "detail": "no unexpected support documents"
                if not unexpected
                else f"unexpected: {', '.join(unexpected)}",
            }
        )

    min_returned_sources = case.get("min_returned_sources")
    if min_returned_sources is not None:
        minimum = int(min_returned_sources)
        checks.append(
            {
                "name": "min_returned_sources",
                "passed": len(sources) >= minimum,
                "detail": f"{len(sources)} returned, expected at least {minimum}",
            }
        )

    max_returned_sources = case.get("max_returned_sources")
    if max_returned_sources is not None:
        maximum = int(max_returned_sources)
        checks.append(
            {
                "name": "max_returned_sources",
                "passed": len(sources) <= maximum,
                "detail": f"{len(sources)} returned, expected at most {maximum}",
            }
        )

    expected_mode = case.get("expected_mode")
    if expected_mode is not None:
        checks.append(
            {
                "name": "expected_mode",
                "passed": debug.mode == expected_mode,
                "detail": f"mode={debug.mode}, expected={expected_mode}",
            }
        )

    min_confidence = case.get("min_confidence")
    if min_confidence is not None:
        minimum = str(min_confidence)
        checks.append(
            {
                "name": "min_confidence",
                "passed": confidence_at_least(debug.confidence, minimum),
                "detail": f"confidence={debug.confidence}, expected>={minimum}",
            }
        )

    reply = None
    if with_replies:
        payload_module = __import__("app.schemas.chat", fromlist=["ChatRequest"])
        ChatRequest = getattr(payload_module, "ChatRequest")
        response = orchestrator.respond(
            ChatRequest(
                message=question,
                history=[],
                document_ids=scope_ids,
                persist_conversation=False,
            )
        )
        reply = response.reply
        normalized_reply = normalize_text(reply)

        expected_reply_terms = [str(term).lower() for term in case.get("expected_reply_terms", [])]
        if expected_reply_terms:
            missing_terms = [
                term for term in expected_reply_terms if term not in normalized_reply
            ]
            checks.append(
                {
                    "name": "expected_reply_terms",
                    "passed": not missing_terms,
                    "detail": "all expected reply terms present"
                    if not missing_terms
                    else f"missing terms: {', '.join(missing_terms)}",
                }
            )

        forbidden_reply_terms = [
            str(term).lower() for term in case.get("forbidden_reply_terms", [])
        ]
        if forbidden_reply_terms:
            found_terms = [
                term for term in forbidden_reply_terms if term in normalized_reply
            ]
            checks.append(
                {
                    "name": "forbidden_reply_terms",
                    "passed": not found_terms,
                    "detail": "no forbidden reply terms found"
                    if not found_terms
                    else f"forbidden terms present: {', '.join(found_terms)}",
                }
            )

    passed = all(check["passed"] for check in checks)
    return {
        "id": case.get("id", question),
        "question": question,
        "scope_documents": scope_names,
        "returned_documents": returned_documents,
        "returned_sources": len(sources),
        "mode": debug.mode,
        "confidence": debug.confidence,
        "top_source_score": debug.top_source_score,
        "checks": checks,
        "passed": passed,
        "skipped": False,
        "skip_reason": None,
        "reply": reply,
    }


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    os.chdir(repo_root)

    suite_path = (repo_root / args.suite).resolve()
    suite = load_suite(suite_path)
    orchestrator, document_service = load_backend()
    name_to_id, _ = document_maps(document_service)

    cases = suite.get("cases", [])
    results = [
        run_case(
            orchestrator=orchestrator,
            document_service=document_service,
            name_to_id=name_to_id,
            case=case,
            with_replies=args.with_replies,
        )
        for case in cases
    ]

    skipped_count = sum(1 for result in results if result.get("skipped"))
    executed_results = [result for result in results if not result.get("skipped")]
    passed_count = sum(1 for result in executed_results if result["passed"])
    total_count = len(executed_results)

    print(f"Eval suite: {suite.get('name', suite_path.name)}")
    print(f"Cases: {passed_count}/{total_count} passed")
    if skipped_count:
        print(f"Skipped: {skipped_count}")
    print("")

    for result in results:
        if result.get("skipped"):
            print(f"[SKIP] {result['id']} | {result['skip_reason']}")
            print("")
            continue

        status = "PASS" if result["passed"] else "FAIL"
        print(
            f"[{status}] {result['id']} | mode={result['mode']} | "
            f"confidence={result['confidence']} | sources={result['returned_sources']} | "
            f"docs={', '.join(result['returned_documents']) or 'none'}"
        )
        for check in result["checks"]:
            prefix = "  - OK" if check["passed"] else "  - FAIL"
            print(f"{prefix} {check['name']}: {check['detail']}")
        if args.with_replies and result["reply"]:
            safe_print(f"  Reply: {result['reply'][:220]}")
        print("")

    report = {
        "suite": suite.get("name", suite_path.name),
        "with_replies": args.with_replies,
        "passed_cases": passed_count,
        "total_cases": total_count,
        "skipped_cases": skipped_count,
        "results": results,
    }

    if args.write_report:
        report_path = (repo_root / args.write_report).resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        print(f"Report written to {report_path}")

    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
