from __future__ import annotations

import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from gliner import GLiNER  # noqa: E402

from app.services.documents import DocumentService  # noqa: E402


GLINER_MODEL_ID = os.environ.get("GLINER_MODEL_ID", "urchade/gliner_small-v2.1")
GLINER_LABELS = [
    "company",
    "organization",
    "person",
    "project",
    "product",
    "date",
    "location",
    "invoice number",
    "contract name",
    "policy name",
]
TARGET_TYPES = [
    "invoice",
    "contract",
    "policy",
    "insurance",
    "architecture",
    "roadmap",
    "report",
    "document",
]


def safe_print(value: str) -> None:
    normalized = value.encode("cp1252", errors="replace").decode("cp1252")
    print(normalized)


def normalize_preview(value: str, limit: int = 240) -> str:
    return " ".join(value.split())[:limit]


def choose_default_documents(service: DocumentService) -> list[str]:
    selected: list[str] = []
    seen_ids: set[str] = set()
    documents = service.list_documents()

    for target_type in TARGET_TYPES:
        match = next(
            (
                document
                for document in documents
                if document.detected_document_type == target_type and document.id not in seen_ids
            ),
            None,
        )
        if match is None:
            continue
        selected.append(match.original_name)
        seen_ids.add(match.id)
        if len(selected) >= 6:
            break

    if selected:
        return selected

    return [document.original_name for document in documents[:6]]


def load_extracted_text(service: DocumentService, document_id: str) -> str:
    extracted_path = service.extracted_text_dir / f"{document_id}.txt"
    if not extracted_path.exists():
        return ""
    return extracted_path.read_text(encoding="utf-8")


def summarize_current_entities(document) -> dict[str, object]:
    entity_signals = [
        {
            "value": signal.value,
            "score": round(float(signal.score), 3),
            "source": signal.source,
        }
        for signal in document.document_signals
        if signal.category == "entity"
    ]
    return {
        "entities": document.document_entities[:12],
        "entity_signals": entity_signals[:12],
    }


def summarize_gliner_predictions(model: GLiNER, text: str) -> dict[str, object]:
    if not text.strip():
        return {"entities": [], "label_counts": {}}

    predictions = model.predict_entities(
        text[:5000],
        GLINER_LABELS,
        threshold=0.35,
    )
    normalized_predictions: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str]] = set()
    for prediction in predictions:
        label = str(prediction.get("label", "")).strip()
        entity_text = " ".join(str(prediction.get("text", "")).split()).strip()
        if not label or not entity_text:
            continue
        key = (label.lower(), entity_text.lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        normalized_predictions.append(
            {
                "label": label,
                "text": entity_text,
                "score": round(float(prediction.get("score", 0.0)), 3),
            }
        )

    normalized_predictions.sort(
        key=lambda item: (float(item["score"]), len(str(item["text"]))),
        reverse=True,
    )
    label_counts: dict[str, int] = {}
    for item in normalized_predictions:
        label_counts[item["label"]] = label_counts.get(item["label"], 0) + 1

    return {
        "entities": normalized_predictions[:15],
        "label_counts": label_counts,
    }


def main() -> int:
    service = DocumentService()
    selected_names = sys.argv[1:] or choose_default_documents(service)
    documents = service.list_documents()

    safe_print(f"GLiNER model: {GLINER_MODEL_ID}")
    model = GLiNER.from_pretrained(GLINER_MODEL_ID)

    for name in selected_names:
        document = next((item for item in documents if item.original_name == name), None)
        safe_print(f"\n=== {name} ===")
        if document is None:
            safe_print("Document not found in metadata.")
            continue

        extracted_text = load_extracted_text(service, document.id)
        current_summary = summarize_current_entities(document)
        gliner_summary = summarize_gliner_predictions(model, extracted_text)

        payload = {
            "type": document.detected_document_type,
            "date": document.document_date,
            "ocr_used": document.ocr_used,
            "preview": normalize_preview(extracted_text),
            "current": current_summary,
            "gliner": gliner_summary,
        }
        safe_print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
