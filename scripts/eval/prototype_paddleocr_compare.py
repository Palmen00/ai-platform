from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import time

import fitz
from paddleocr import PaddleOCR

REPO_ROOT = Path(__file__).resolve().parents[2]


DEFAULT_SUITE = REPO_ROOT / "backend" / "evals" / "ocr_engine_cases.json"
DOCUMENTS_DIR = REPO_ROOT / "data" / "app" / "documents"
EXTRACTED_DIR = DOCUMENTS_DIR / "extracted"
UPLOADS_DIR = REPO_ROOT / "data" / "uploads"


def normalize(value: str) -> str:
    normalized = value.lower()
    replacements = {
        "å": "a",
        "ä": "a",
        "ö": "o",
        "é": "e",
        "ü": "u",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def safe_print(value: str) -> None:
    print(value.encode("utf-8", errors="replace").decode("utf-8"))


def render_pdf_pages(pdf_path: Path, pages: list[int]) -> list[Path]:
    output_paths: list[Path] = []
    with fitz.open(pdf_path) as pdf:
        for page_index in pages:
            if page_index >= pdf.page_count:
                continue
            page = pdf.load_page(page_index)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            output_path = REPO_ROOT / "temp" / f"paddleocr_{pdf_path.stem}_page_{page_index + 1}.png"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            pix.save(output_path)
            output_paths.append(output_path)
    return output_paths


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


def flatten_paddle_result(result: object) -> str:
    chunks: list[str] = []
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                rec_texts = item.get("rec_texts")
                if isinstance(rec_texts, list):
                    chunks.extend(str(text) for text in rec_texts if str(text).strip())
                    continue
            chunks.append(str(item))
    else:
        chunks.append(str(result))
    return "\n".join(chunks).strip()


def paddle_extract(image_paths: list[Path], languages: list[str]) -> tuple[str, float, float]:
    lang = "en"
    if any(language.lower().startswith("sv") for language in languages):
        lang = "en"

    init_start = time.perf_counter()
    ocr = PaddleOCR(lang=lang)
    init_seconds = time.perf_counter() - init_start

    text_parts: list[str] = []
    ocr_start = time.perf_counter()
    for image_path in image_paths:
        result = ocr.predict(str(image_path))
        flattened = flatten_paddle_result(result)
        if flattened:
            text_parts.append(flattened)
    ocr_seconds = time.perf_counter() - ocr_start
    return "\n".join(text_parts).strip(), init_seconds, ocr_seconds


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
        "paddle_passed": 0,
        "paddle_failed": 0,
        "current_passed": 0,
        "current_failed": 0,
        "total": len(cases),
    }
    reports: list[dict[str, object]] = []

    safe_print(f"Running PaddleOCR compare: {suite_path}")

    for case in cases:
        document = documents_by_name.get(case["document"])
        if document is None:
            reports.append({"id": case["id"], "status": "missing"})
            safe_print(f"- {case['id']}: missing")
            continue

        pdf_path = UPLOADS_DIR / str(document["stored_name"])
        image_paths = render_pdf_pages(pdf_path, [int(page) for page in case.get("pages", [0])])
        paddle_text, init_seconds, ocr_seconds = paddle_extract(
            image_paths=image_paths,
            languages=[str(item) for item in case.get("languages", ["en"])],
        )
        current_text = current_extract(str(document["id"]))

        expected_terms = [str(item) for item in case.get("expected_terms", [])]
        min_term_hits = int(case.get("min_term_hits", len(expected_terms)))

        paddle_hits_count, paddle_hits = term_hits(paddle_text, expected_terms)
        current_hits_count, current_hits = term_hits(current_text, expected_terms)

        paddle_status = "passed" if paddle_hits_count >= min_term_hits else "failed"
        current_status = "passed" if current_hits_count >= min_term_hits else "failed"

        summary[f"paddle_{paddle_status}"] += 1
        summary[f"current_{current_status}"] += 1

        reports.append(
            {
                "id": case["id"],
                "document": str(document["original_name"]),
                "paddleocr": {
                    "status": paddle_status,
                    "init_seconds": round(init_seconds, 3),
                    "ocr_seconds": round(ocr_seconds, 3),
                    "term_hits": paddle_hits,
                    "term_hit_count": paddle_hits_count,
                    "preview": paddle_text[:1200],
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
            f"- {case['id']}: paddle={paddle_status} ({paddle_hits_count} hits, "
            f"init={init_seconds:.2f}s, ocr={ocr_seconds:.2f}s) | current={current_status} ({current_hits_count} hits)"
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
