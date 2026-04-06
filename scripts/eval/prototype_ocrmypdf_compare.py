from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import time

import fitz

REPO_ROOT = Path(__file__).resolve().parents[2]


DEFAULT_SUITE = REPO_ROOT / "backend" / "evals" / "ocr_engine_cases.json"
DOCUMENTS_DIR = REPO_ROOT / "data" / "app" / "documents"
EXTRACTED_DIR = DOCUMENTS_DIR / "extracted"
UPLOADS_DIR = REPO_ROOT / "data" / "uploads"

TESSERACT_LANGUAGE_MAP = {
    "en": "eng",
    "eng": "eng",
    "sv": "swe",
    "swe": "swe",
}


def normalize(value: str) -> str:
    normalized = value.lower()
    replacements = {
        "Ã¥": "a",
        "Ã¤": "a",
        "Ã¶": "o",
        "Ã©": "e",
        "Ã¼": "u",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def safe_print(value: str) -> None:
    print(value.encode("utf-8", errors="replace").decode("utf-8"))


def load_documents_by_name() -> dict[str, dict[str, object]]:
    documents: dict[str, dict[str, object]] = {}
    for path in DOCUMENTS_DIR.glob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        documents[str(payload.get("original_name", ""))] = payload
    return documents


def current_extract(document_id: str) -> str:
    text_path = EXTRACTED_DIR / f"{document_id}.txt"
    if not text_path.exists():
        return ""
    return text_path.read_text(encoding="utf-8")


def term_hits(text: str, expected_terms: list[str]) -> tuple[int, list[str]]:
    normalized_text = normalize(text)
    hits: list[str] = []
    for term in expected_terms:
        if normalize(term) in normalized_text:
            hits.append(term)
    return len(hits), hits


def extract_pdf_text(pdf_path: Path, pages: list[int]) -> str:
    parts: list[str] = []
    with fitz.open(pdf_path) as pdf:
        for page_index in pages:
            if page_index >= pdf.page_count:
                continue
            parts.append(pdf.load_page(page_index).get_text("text"))
    return "\n".join(part for part in parts if part.strip()).strip()


def resolve_ocr_languages(languages: list[str]) -> str:
    resolved: list[str] = []
    for language in languages:
        mapped = TESSERACT_LANGUAGE_MAP.get(language.lower())
        if mapped and mapped not in resolved:
            resolved.append(mapped)
    if not resolved:
        resolved.append("eng")
    return "+".join(resolved)


def ocrmypdf_extract(
    pdf_path: Path,
    pages: list[int],
    languages: list[str],
) -> tuple[str, float]:
    temp_dir = REPO_ROOT / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_path = temp_dir / f"ocrmypdf_{pdf_path.stem}.pdf"
    if output_path.exists():
        output_path.unlink()

    language_arg = resolve_ocr_languages(languages)
    command = [
        "ocrmypdf",
        "--force-ocr",
        "--skip-big",
        "50",
        "--optimize",
        "0",
        "--output-type",
        "pdf",
        "--sidecar",
        "/dev/null",
        "-l",
        language_arg,
        str(pdf_path),
        str(output_path),
    ]

    start = time.perf_counter()
    subprocess.run(command, check=True, capture_output=True, text=True)
    elapsed_seconds = time.perf_counter() - start
    text = extract_pdf_text(output_path, pages)
    return text, elapsed_seconds


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default=str(DEFAULT_SUITE))
    parser.add_argument("--write-report", default="")
    args = parser.parse_args()

    suite_path = Path(args.suite)
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    cases = suite.get("cases", [])
    documents_by_name = load_documents_by_name()

    summary = {
        "ocrmypdf_passed": 0,
        "ocrmypdf_failed": 0,
        "current_passed": 0,
        "current_failed": 0,
        "total": len(cases),
    }
    reports: list[dict[str, object]] = []

    safe_print(f"Running OCRmyPDF compare: {suite_path}")

    for case in cases:
        document = documents_by_name.get(case["document"])
        if document is None:
            reports.append({"id": case["id"], "status": "missing"})
            safe_print(f"- {case['id']}: missing")
            continue

        pdf_path = UPLOADS_DIR / str(document["stored_name"])
        pages = [int(page) for page in case.get("pages", [0])]
        ocrmypdf_text, ocr_seconds = ocrmypdf_extract(
            pdf_path=pdf_path,
            pages=pages,
            languages=[str(item) for item in case.get("languages", ["en"])],
        )
        current_text = current_extract(str(document["id"]))

        expected_terms = [str(item) for item in case.get("expected_terms", [])]
        min_term_hits = int(case.get("min_term_hits", len(expected_terms)))

        ocrmypdf_hits_count, ocrmypdf_hits = term_hits(ocrmypdf_text, expected_terms)
        current_hits_count, current_hits = term_hits(current_text, expected_terms)

        ocrmypdf_status = "passed" if ocrmypdf_hits_count >= min_term_hits else "failed"
        current_status = "passed" if current_hits_count >= min_term_hits else "failed"

        summary[f"ocrmypdf_{ocrmypdf_status}"] += 1
        summary[f"current_{current_status}"] += 1

        reports.append(
            {
                "id": case["id"],
                "document": str(document["original_name"]),
                "ocrmypdf": {
                    "status": ocrmypdf_status,
                    "ocr_seconds": round(ocr_seconds, 3),
                    "term_hits": ocrmypdf_hits,
                    "term_hit_count": ocrmypdf_hits_count,
                    "preview": ocrmypdf_text[:1200],
                },
                "current": {
                    "status": current_status,
                    "term_hits": current_hits,
                    "term_hit_count": current_hits_count,
                    "preview": current_text[:1200],
                },
            }
        )

        safe_print(
            f"- {case['id']}: ocrmypdf={ocrmypdf_status} ({ocrmypdf_hits_count} hits, "
            f"ocr={ocr_seconds:.2f}s) | current={current_status} ({current_hits_count} hits)"
        )

    safe_print("Summary: " + ", ".join(f"{key}={value}" for key, value in summary.items()))

    report = {
        "suite": str(suite_path),
        "summary": summary,
        "cases": reports,
    }
    if args.write_report:
        report_path = Path(args.write_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        safe_print(f"Wrote report: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
