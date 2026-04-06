from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
import re
import sys

os.environ.setdefault("UNSTRUCTURED_ENABLED", "true")
os.environ.setdefault("GLINER_ENABLED", "false")

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.documents import DocumentService  # noqa: E402
from app.services.unstructured_service import UnstructuredPartitionService  # noqa: E402


DEFAULT_SUITE = REPO_ROOT / "backend" / "evals" / "unstructured_structure_cases.json"


@dataclass
class PipelineResult:
    title: str
    section_titles: list[str]
    title_hits: int
    section_hits: int
    min_section_ratio: float
    score: float


def normalize(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def score_pipeline(
    *,
    title: str,
    section_titles: list[str],
    expected_title_terms: list[str],
    expected_section_terms: list[str],
    min_sections: int,
) -> PipelineResult:
    normalized_title = normalize(title)
    normalized_sections = [normalize(section_title) for section_title in section_titles if section_title.strip()]
    title_hits = sum(1 for term in expected_title_terms if normalize(term) in normalized_title)
    section_hits = 0
    for term in expected_section_terms:
        normalized_term = normalize(term)
        if any(normalized_term in section for section in normalized_sections):
            section_hits += 1

    min_section_ratio = min(len(normalized_sections) / max(min_sections, 1), 1.0) if min_sections > 0 else 1.0

    title_score = (title_hits / max(len(expected_title_terms), 1)) * 0.4
    section_score = (section_hits / max(len(expected_section_terms), 1)) * 0.5
    count_score = min_section_ratio * 0.1
    total_score = round(title_score + section_score + count_score, 4)

    return PipelineResult(
        title=title,
        section_titles=section_titles,
        title_hits=title_hits,
        section_hits=section_hits,
        min_section_ratio=round(min_section_ratio, 4),
        score=total_score,
    )


def unique_titles(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = normalize(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(value.strip())
    return ordered


def infer_content_type(name: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".md":
        return "text/markdown"
    return "text/plain"


def current_pipeline_result(service: DocumentService, document) -> tuple[str, list[str]]:
    chunks_path = service.chunks_dir / f"{document.id}.json"
    chunks = json.loads(chunks_path.read_text(encoding="utf-8")) if chunks_path.exists() else []
    section_titles = unique_titles([str(chunk.get("section_title") or "").strip() for chunk in chunks])
    title = str(getattr(document, "document_title", "") or "").strip() or Path(document.original_name).stem
    return title, section_titles


def unstructured_pipeline_result(service: DocumentService, document) -> tuple[str, list[str]]:
    partition_service = UnstructuredPartitionService()
    file_path = service.uploads_dir / document.stored_name
    content_type = str(getattr(document, "content_type", "") or infer_content_type(document.original_name))
    title = partition_service.extract_document_title(
        file_path=file_path,
        content_type=content_type,
    ) or Path(document.original_name).stem
    sections = partition_service.extract_sections(
        file_path=file_path,
        content_type=content_type,
        fallback_title=Path(document.original_name).stem,
    )
    section_titles = unique_titles([str(section.get("title") or "").strip() for section in sections])
    return title, section_titles


def safe_print(value: str) -> None:
    print(value.encode("cp1252", errors="replace").decode("cp1252"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default=str(DEFAULT_SUITE))
    parser.add_argument("--write-report", default="")
    args = parser.parse_args()

    suite_path = Path(args.suite)
    cases = json.loads(suite_path.read_text(encoding="utf-8"))
    service = DocumentService()
    documents_by_name = {document.original_name: document for document in service.list_documents()}

    summary = {
        "improved": 0,
        "unchanged": 0,
        "regressed": 0,
        "missing": 0,
        "total": len(cases),
    }
    case_reports: list[dict[str, object]] = []

    safe_print(f"Running Unstructured structure eval: {suite_path}")

    for case in cases:
        document_name = case["document"]
        document = documents_by_name.get(document_name)
        if document is None:
            summary["missing"] += 1
            case_reports.append({"id": case["id"], "document": document_name, "status": "missing"})
            safe_print(f"- {case['id']}: missing document")
            continue

        expected_title_terms = [str(item) for item in case.get("expected_title_terms", [])]
        expected_section_terms = [str(item) for item in case.get("expected_section_terms", [])]
        min_sections = int(case.get("min_sections", 0))

        current_title, current_sections = current_pipeline_result(service, document)
        unstructured_title, unstructured_sections = unstructured_pipeline_result(service, document)

        current_result = score_pipeline(
            title=current_title,
            section_titles=current_sections,
            expected_title_terms=expected_title_terms,
            expected_section_terms=expected_section_terms,
            min_sections=min_sections,
        )
        unstructured_result = score_pipeline(
            title=unstructured_title,
            section_titles=unstructured_sections,
            expected_title_terms=expected_title_terms,
            expected_section_terms=expected_section_terms,
            min_sections=min_sections,
        )

        delta = round(unstructured_result.score - current_result.score, 4)
        if delta > 0.02:
            status = "improved"
            summary["improved"] += 1
        elif delta < -0.02:
            status = "regressed"
            summary["regressed"] += 1
        else:
            status = "unchanged"
            summary["unchanged"] += 1

        case_reports.append(
            {
                "id": case["id"],
                "document": document_name,
                "category": case.get("category", ""),
                "status": status,
                "delta": delta,
                "current": asdict(current_result),
                "unstructured": asdict(unstructured_result),
            }
        )

        safe_print(
            f"- {case['id']}: {status} "
            f"(current={current_result.score:.2f}, unstructured={unstructured_result.score:.2f}, delta={delta:+.2f})"
        )

    report = {"suite": str(suite_path), "summary": summary, "cases": case_reports}

    safe_print("Summary: " + ", ".join(f"{key}={value}" for key, value in summary.items()))

    if args.write_report:
        report_path = Path(args.write_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        safe_print(f"Wrote report: {report_path}")

    return 0 if summary["regressed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
