from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT / "scripts" / "eval"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from prototype_document_profile import (  # noqa: E402
    clean_json_candidate,
    generate_document_profile,
    normalize_name,
    safe_print,
)


DEFAULT_SUITE = REPO_ROOT / "backend" / "evals" / "document_profile_cases.json"


def normalize(value: str) -> str:
    lowered = normalize_name(value)
    return re.sub(r"\s+", " ", lowered).strip()


def flatten_profile_terms(profile: dict[str, object], field_name: str) -> list[str]:
    raw_value = profile.get(field_name)
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        return [raw_value]
    if isinstance(raw_value, list):
        flattened: list[str] = []
        for item in raw_value:
            if isinstance(item, str):
                flattened.append(item)
            elif isinstance(item, dict):
                flattened.extend(str(value) for value in item.values() if value is not None)
        return flattened
    return [str(raw_value)]


def contains_term(values: list[str], term: str) -> bool:
    normalized_term = normalize(term)
    return any(normalized_term in normalize(value) for value in values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default=str(DEFAULT_SUITE))
    parser.add_argument("--write-report", default="")
    args = parser.parse_args()

    suite_path = Path(args.suite)
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    cases = suite.get("cases", [])

    summary = {
        "passed": 0,
        "failed": 0,
        "total": len(cases),
    }
    report_cases: list[dict[str, object]] = []

    safe_print(f"Running document profile eval: {suite_path}")

    for case in cases:
        case_id = str(case["id"])
        document_name = str(case["document"])
        result = generate_document_profile(document_name)
        failures: list[str] = []

        if result.get("status") != "ok":
            failures.append(f"status={result.get('status')}")
            profile = {}
        else:
            profile = dict(result.get("profile") or {})

        profile_type = str(profile.get("document_type") or "")
        summary_text = str(profile.get("summary") or "")
        entity_values = flatten_profile_terms(profile, "entities")
        search_clues = flatten_profile_terms(profile, "search_clues")
        date_values = [value for value in flatten_profile_terms(profile, "important_dates") if re.search(r"\d{4}-\d{2}-\d{2}", value)]
        confidence = str(profile.get("confidence") or "").lower()

        for term in case.get("expected_type_terms", []):
            if not contains_term([profile_type], str(term)):
                failures.append(f"missing type term: {term}")

        for term in case.get("expected_summary_terms", []):
            if not contains_term([summary_text], str(term)):
                failures.append(f"missing summary term: {term}")

        for term in case.get("expected_entity_terms", []):
            if not contains_term(entity_values, str(term)):
                failures.append(f"missing entity term: {term}")

        for term in case.get("expected_search_clue_terms", []):
            if not contains_term(search_clues, str(term)):
                failures.append(f"missing search clue term: {term}")

        for value in case.get("expected_date_values", []):
            if str(value) not in date_values:
                failures.append(f"missing date value: {value}")

        allowed_confidence = [str(item).lower() for item in case.get("allowed_confidence", [])]
        if allowed_confidence and confidence not in allowed_confidence:
            failures.append(f"confidence {confidence or 'missing'} not in {allowed_confidence}")

        status = "passed" if not failures else "failed"
        if status == "passed":
            summary["passed"] += 1
        else:
            summary["failed"] += 1

        safe_print(f"- {case_id}: {status}")
        if failures:
            for failure in failures:
                safe_print(f"  - {failure}")

        report_cases.append(
            {
                "id": case_id,
                "document": document_name,
                "status": status,
                "failures": failures,
                "result": result,
            }
        )

    safe_print(
        "Summary: "
        + ", ".join(f"{key}={value}" for key, value in summary.items())
    )

    report = {
        "suite": str(suite_path),
        "summary": summary,
        "cases": report_cases,
    }

    if args.write_report:
        report_path = Path(args.write_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        safe_print(f"Wrote report: {report_path}")

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
