from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
import re
import sys

os.environ.setdefault("UNSTRUCTURED_ENABLED", "true")
os.environ.setdefault("GLINER_ENABLED", "false")

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from docling.document_converter import DocumentConverter  # noqa: E402

from app.services.documents import DocumentService  # noqa: E402
from app.services.unstructured_service import UnstructuredPartitionService  # noqa: E402


DEFAULT_SUITE = REPO_ROOT / "backend" / "evals" / "docling_structure_cases.json"


@dataclass
class PipelineResult:
    title: str
    headings: list[str]
    title_hits: int
    heading_hits: int
    content_hits: int
    min_heading_ratio: float
    score: float
    duration_seconds: float


def normalize(value: str) -> str:
    normalized = value.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


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


def safe_print(value: str) -> None:
    print(value.encode("cp1252", errors="replace").decode("cp1252"))


def heading_hits(headings: list[str], expected_terms: list[str]) -> int:
    normalized_headings = [normalize(item) for item in headings if item.strip()]
    hits = 0
    for term in expected_terms:
        normalized_term = normalize(term)
        if any(normalized_term in heading for heading in normalized_headings):
            hits += 1
    return hits


def content_hits(content: str, expected_terms: list[str]) -> int:
    normalized_content = normalize(content)
    return sum(1 for term in expected_terms if normalize(term) in normalized_content)


def score_pipeline(
    *,
    title: str,
    headings: list[str],
    content: str,
    expected_title_terms: list[str],
    expected_heading_terms: list[str],
    expected_content_terms: list[str],
    min_headings: int,
    duration_seconds: float,
) -> PipelineResult:
    normalized_title = normalize(title)
    title_hits = sum(1 for term in expected_title_terms if normalize(term) in normalized_title)
    heading_hit_count = heading_hits(headings, expected_heading_terms)
    content_hit_count = content_hits(content, expected_content_terms)
    min_heading_ratio = min(len(headings) / max(min_headings, 1), 1.0) if min_headings > 0 else 1.0

    title_score = (title_hits / max(len(expected_title_terms), 1)) * 0.30
    heading_score = (heading_hit_count / max(len(expected_heading_terms), 1)) * 0.30
    content_score = (content_hit_count / max(len(expected_content_terms), 1)) * 0.30
    count_score = min_heading_ratio * 0.10
    total_score = round(title_score + heading_score + content_score + count_score, 4)

    return PipelineResult(
        title=title,
        headings=headings,
        title_hits=title_hits,
        heading_hits=heading_hit_count,
        content_hits=content_hit_count,
        min_heading_ratio=round(min_heading_ratio, 4),
        score=total_score,
        duration_seconds=round(duration_seconds, 3),
    )


def current_pipeline_result(service: DocumentService, document) -> tuple[str, list[str], str]:
    chunks_path = service.chunks_dir / f"{document.id}.json"
    chunks = json.loads(chunks_path.read_text(encoding="utf-8")) if chunks_path.exists() else []
    headings = unique_titles([str(chunk.get("section_title") or "").strip() for chunk in chunks])
    extracted_path = service.extracted_text_dir / f"{document.id}.txt"
    content = extracted_path.read_text(encoding="utf-8") if extracted_path.exists() else ""
    title = str(getattr(document, "document_title", "") or "").strip() or Path(document.original_name).stem
    return title, headings, content


def unstructured_pipeline_result(service: DocumentService, document) -> tuple[str, list[str], str]:
    partition_service = UnstructuredPartitionService()
    file_path = service.uploads_dir / document.stored_name
    content_type = str(getattr(document, "content_type", "") or "application/pdf")
    title = partition_service.extract_document_title(
        file_path=file_path,
        content_type=content_type,
    ) or Path(document.original_name).stem
    sections = partition_service.extract_sections(
        file_path=file_path,
        content_type=content_type,
        fallback_title=Path(document.original_name).stem,
    )
    headings = unique_titles([str(section.get("title") or "").strip() for section in sections])
    content = "\n".join(
        str(section.get("text") or "").strip()
        for section in sections
        if str(section.get("text") or "").strip()
    )
    return title, headings, content


def docling_pipeline_result(converter: DocumentConverter, service: DocumentService, document) -> tuple[str, list[str], str]:
    file_path = service.uploads_dir / document.stored_name
    result = converter.convert(str(file_path.resolve()))
    markdown = result.document.export_to_markdown()
    headings: list[str] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        headings.append(stripped.lstrip("#").strip())
    headings = unique_titles(headings)
    title = headings[0] if headings else Path(document.original_name).stem
    return title, headings, markdown


def evaluate_pipeline(fetcher, *args, **kwargs) -> tuple[PipelineResult, str | None]:
    started = perf_counter()
    try:
        title, headings, content = fetcher(*args, **kwargs)
        duration = perf_counter() - started
        return (
            score_pipeline(
                title=title,
                headings=headings,
                content=content,
                expected_title_terms=kwargs["expected_title_terms"],
                expected_heading_terms=kwargs["expected_heading_terms"],
                expected_content_terms=kwargs["expected_content_terms"],
                min_headings=kwargs["min_headings"],
                duration_seconds=duration,
            ),
            None,
        )
    except Exception as exc:  # pragma: no cover - prototype comparison
        return (
            PipelineResult(
                title="",
                headings=[],
                title_hits=0,
                heading_hits=0,
                content_hits=0,
                min_heading_ratio=0.0,
                score=0.0,
                duration_seconds=round(perf_counter() - started, 3),
            ),
            str(exc),
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default=str(DEFAULT_SUITE))
    parser.add_argument("--write-report", default="")
    args = parser.parse_args()

    suite_path = Path(args.suite)
    cases = json.loads(suite_path.read_text(encoding="utf-8"))
    service = DocumentService()
    converter = DocumentConverter()
    documents_by_name = {document.original_name: document for document in service.list_documents()}

    summary: dict[str, object] = {
        "best_counts": {"current": 0, "unstructured": 0, "docling": 0},
        "average_scores": {"current": 0.0, "unstructured": 0.0, "docling": 0.0},
        "average_duration_seconds": {"current": 0.0, "unstructured": 0.0, "docling": 0.0},
        "missing": 0,
        "total": len(cases),
    }
    reports: list[dict[str, object]] = []
    aggregate_scores = {"current": [], "unstructured": [], "docling": []}
    aggregate_durations = {"current": [], "unstructured": [], "docling": []}

    safe_print(f"Running Docling comparison suite: {suite_path}")

    for case in cases:
        document_name = case["document"]
        document = documents_by_name.get(document_name)
        if document is None:
            summary["missing"] = int(summary["missing"]) + 1
            reports.append({"id": case["id"], "document": document_name, "status": "missing"})
            safe_print(f"- {case['id']}: missing document")
            continue

        shared_kwargs = {
            "expected_title_terms": [str(item) for item in case.get("expected_title_terms", [])],
            "expected_heading_terms": [str(item) for item in case.get("expected_heading_terms", [])],
            "expected_content_terms": [str(item) for item in case.get("expected_content_terms", [])],
            "min_headings": int(case.get("min_headings", 0)),
        }

        current_result, current_error = evaluate_pipeline(
            lambda **_: current_pipeline_result(service, document),
            **shared_kwargs,
        )
        unstructured_result, unstructured_error = evaluate_pipeline(
            lambda **_: unstructured_pipeline_result(service, document),
            **shared_kwargs,
        )
        docling_result, docling_error = evaluate_pipeline(
            lambda **_: docling_pipeline_result(converter, service, document),
            **shared_kwargs,
        )

        result_map = {
            "current": current_result,
            "unstructured": unstructured_result,
            "docling": docling_result,
        }
        best_pipeline = max(result_map.items(), key=lambda item: item[1].score)[0]
        summary["best_counts"][best_pipeline] += 1

        for key, value in result_map.items():
            aggregate_scores[key].append(value.score)
            aggregate_durations[key].append(value.duration_seconds)

        reports.append(
            {
                "id": case["id"],
                "document": document_name,
                "category": case.get("category", ""),
                "best_pipeline": best_pipeline,
                "current": asdict(current_result),
                "unstructured": asdict(unstructured_result),
                "docling": asdict(docling_result),
                "errors": {
                    "current": current_error,
                    "unstructured": unstructured_error,
                    "docling": docling_error,
                },
            }
        )

        safe_print(
            f"- {case['id']}: best={best_pipeline} "
            f"(current={current_result.score:.2f}, unstructured={unstructured_result.score:.2f}, docling={docling_result.score:.2f})"
        )

    for key in aggregate_scores:
        if aggregate_scores[key]:
            summary["average_scores"][key] = round(sum(aggregate_scores[key]) / len(aggregate_scores[key]), 4)
        if aggregate_durations[key]:
            summary["average_duration_seconds"][key] = round(
                sum(aggregate_durations[key]) / len(aggregate_durations[key]),
                3,
            )

    safe_print(
        "Summary: "
        + ", ".join(
            [
                f"best_current={summary['best_counts']['current']}",
                f"best_unstructured={summary['best_counts']['unstructured']}",
                f"best_docling={summary['best_counts']['docling']}",
                f"missing={summary['missing']}",
            ]
        )
    )

    report = {"suite": str(suite_path), "summary": summary, "cases": reports}
    if args.write_report:
        report_path = Path(args.write_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        safe_print(f"Wrote report: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
