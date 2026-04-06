from __future__ import annotations

from collections import Counter
import os
from pathlib import Path
import json
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.documents import DocumentService  # noqa: E402
from unstructured.partition.auto import partition  # noqa: E402


DEFAULT_DOCUMENTS = [
    "ARCHITECTURE.pdf",
    "local_ai_operating_environment.pdf",
    "Dokument_2023-10-31_180442.pdf",
    "Hash Crack_ Password Cracking Manual v2_0 -- By Joshua Picolet -- 2, Herndon, Virginia, September 1, 2017 -- CreateSpace Independent Publishing -- 9781975924584 -- 7931efa5f9071465df77e4919972de9f -- Anna’s Archive.pdf",
]


def normalize_preview(value: str, limit: int = 200) -> str:
    return " ".join(value.split())[:limit]


def safe_print(value: str) -> None:
    normalized = value.encode("cp1252", errors="replace").decode("cp1252")
    print(normalized)


def ensure_poppler_path() -> None:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    if not local_app_data:
        return

    package_root = local_app_data / "Microsoft" / "WinGet" / "Packages"
    if not package_root.exists():
        return

    poppler_bins = sorted(
        package_root.glob("oschwartz10612.Poppler_*/*/Library/bin"),
        reverse=True,
    )
    if not poppler_bins:
        return

    poppler_bin = str(poppler_bins[0])
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    if poppler_bin not in path_entries:
        os.environ["PATH"] = poppler_bin + os.pathsep + os.environ.get("PATH", "")


def ensure_tesseract_path() -> None:
    candidate_paths = [
        Path("C:/Program Files/Tesseract-OCR"),
        Path("C:/Program Files (x86)/Tesseract-OCR"),
    ]
    for candidate in candidate_paths:
        executable = candidate / "tesseract.exe"
        if not executable.exists():
            continue

        path_entries = os.environ.get("PATH", "").split(os.pathsep)
        if str(candidate) not in path_entries:
            os.environ["PATH"] = str(candidate) + os.pathsep + os.environ.get("PATH", "")
        os.environ.setdefault("TESSERACT_CMD", str(executable))
        return


def summarize_current_pipeline(service: DocumentService, document_id: str) -> dict[str, object]:
    extracted_path = service.extracted_text_dir / f"{document_id}.txt"
    chunks_path = service.chunks_dir / f"{document_id}.json"
    extracted_text = extracted_path.read_text(encoding="utf-8") if extracted_path.exists() else ""
    chunks = json.loads(chunks_path.read_text(encoding="utf-8")) if chunks_path.exists() else []
    section_titles = [
        str(chunk.get("section_title", "")).strip()
        for chunk in chunks
        if str(chunk.get("section_title", "")).strip()
    ]
    return {
        "text_length": len(extracted_text),
        "chunk_count": len(chunks),
        "section_count": len(set(section_titles)),
        "section_titles": section_titles[:8],
        "preview": normalize_preview(extracted_text),
    }


def summarize_unstructured(file_path: Path) -> dict[str, object]:
    elements = partition(filename=str(file_path))
    element_types = Counter(type(element).__name__ for element in elements)
    section_titles = [
        str(element)
        for element in elements
        if type(element).__name__ in {"Title", "Header"}
    ]
    joined_text = "\n".join(str(element) for element in elements if str(element).strip())
    return {
        "text_length": len(joined_text),
        "element_count": len(elements),
        "element_types": dict(element_types.most_common()),
        "section_titles": section_titles[:8],
        "preview": normalize_preview(joined_text),
    }


def main() -> int:
    names = sys.argv[1:] or DEFAULT_DOCUMENTS
    ensure_poppler_path()
    ensure_tesseract_path()
    service = DocumentService()
    all_documents = service.list_documents()

    for name in names:
        document = next((item for item in all_documents if item.original_name == name), None)
        if document is None:
            print(f"\n=== {name} ===")
            print("Document not found in current metadata.")
            continue

        file_path = service.uploads_dir / document.stored_name
        safe_print(f"\n=== {document.original_name} ===")
        safe_print(f"type={document.detected_document_type} ocr_used={document.ocr_used} date={document.document_date}")

        current_summary = summarize_current_pipeline(service, document.id)
        safe_print("\nCurrent pipeline:")
        safe_print(json.dumps(current_summary, ensure_ascii=False, indent=2))

        safe_print("\nUnstructured:")
        try:
            unstructured_summary = summarize_unstructured(file_path)
            safe_print(json.dumps(unstructured_summary, ensure_ascii=False, indent=2))
        except Exception as exc:
            safe_print(f"Unstructured failed: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
