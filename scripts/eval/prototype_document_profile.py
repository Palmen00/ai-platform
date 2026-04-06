from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

from json_repair import repair_json

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.documents import DocumentService  # noqa: E402
from app.services.ollama import OllamaService  # noqa: E402


DEFAULT_DOCUMENTS = [
    "ARCHITECTURE.pdf",
    "Northstar_Aerotech_Master_Service_Agreement_2026-01-15.txt",
    "BlueHarbor_Medical_Invoice_2026-02-14.txt",
    "Hash Crack_ Password Cracking Manual v2_0 -- By Joshua Picolet -- 2, Herndon, Virginia, September 1, 2017 -- CreateSpace Independent Publishing -- 9781975924584 -- 7931efa5f9071465df77e4919972de9f -- Annaâ€™s Archive.pdf",
]


def safe_print(value: str) -> None:
    print(value.encode("cp1252", errors="replace").decode("cp1252"))


def load_document_text(service: DocumentService, document_id: str) -> str:
    extracted_path = service.extracted_text_dir / f"{document_id}.txt"
    if not extracted_path.exists():
        return ""
    return extracted_path.read_text(encoding="utf-8")


def clean_json_candidate(value: str) -> str:
    candidate = value.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?", "", candidate).strip()
        candidate = re.sub(r"```$", "", candidate).strip()
    first_brace = candidate.find("{")
    last_brace = candidate.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return candidate[first_brace : last_brace + 1].strip()
    return candidate


def normalize_name(value: str) -> str:
    normalized = (
        value.replace("â€™", "'")
        .replace("’", "'")
        .replace("–", "-")
        .replace("—", "-")
    )
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def build_prompt(*, document_name: str, text: str) -> str:
    truncated_text = text[:12000]
    return (
        "You analyze one document and return only valid JSON.\n"
        "Do not add explanations, markdown, code fences, or any text before or after the JSON object.\n"
        "Summarize what the document is, not what the user should do with it.\n"
        "Use a semantic document_type such as architecture, invoice, contract, policy, report, quote, form, receipt, manual, guide, insurance, or roadmap.\n"
        "Do not use generic file-format labels like pdf, txt, document, or file unless the content truly gives no better label.\n"
        "If companies, counterparties, products, or well-known tools appear, include the most important ones in entities.\n"
        "If supplier or customer names appear, include them in search_clues as well.\n"
        "Each important_dates entry must use an ISO value like YYYY-MM-DD when the date is clear, otherwise null.\n"
        "confidence is required and must be exactly one of: low, medium, high.\n"
        "If a field is unknown, use null or an empty list.\n"
        "JSON schema:\n"
        "{\n"
        '  "document_type": "short lowercase label",\n'
        '  "summary": "1-2 sentence summary",\n'
        '  "themes": ["..."],\n'
        '  "entities": ["..."],\n'
        '  "important_dates": [{"label": "...", "value": "YYYY-MM-DD or null"}],\n'
        '  "search_clues": ["short phrases someone may search for"],\n'
        '  "confidence": "low|medium|high"\n'
        "}\n\n"
        f"Document name: {document_name}\n"
        "Document text:\n"
        f"{truncated_text}\n"
    )


def resolve_document(service: DocumentService, name: str):
    all_documents = {document.original_name: document for document in service.list_documents()}
    normalized_documents = {
        normalize_name(document.original_name): document
        for document in all_documents.values()
    }
    document = all_documents.get(name)
    if document is None:
        document = normalized_documents.get(normalize_name(name))
    return document


def generate_document_profile(document_name: str) -> dict[str, object]:
    service = DocumentService()
    ollama = OllamaService()
    document = resolve_document(service, document_name)
    if document is None:
        return {"document": document_name, "status": "missing"}

    text = load_document_text(service, document.id)
    prompt = build_prompt(document_name=document.original_name, text=text)
    response_text = ollama.generate_reply(
        model=ollama.default_model,
        prompt=prompt,
        options={
            "temperature": 0,
            "top_p": 0.9,
        },
    )
    cleaned = clean_json_candidate(response_text)

    try:
        parsed = json.loads(cleaned)
        return {
            "document": document.original_name,
            "status": "ok",
            "current_type": document.detected_document_type,
            "current_date": document.document_date,
            "profile": parsed,
        }
    except json.JSONDecodeError:
        try:
            repaired = repair_json(cleaned)
            parsed = json.loads(repaired)
            return {
                "document": document.original_name,
                "status": "ok",
                "current_type": document.detected_document_type,
                "current_date": document.document_date,
                "profile": parsed,
                "json_repaired": True,
            }
        except Exception:
            return {
                "document": document.original_name,
                "status": "invalid_json",
                "current_type": document.detected_document_type,
                "current_date": document.document_date,
                "raw_response": cleaned,
            }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("documents", nargs="*")
    parser.add_argument("--write-report", default="")
    args = parser.parse_args()

    documents = args.documents or DEFAULT_DOCUMENTS

    report: list[dict[str, object]] = []

    for name in documents:
        result = generate_document_profile(name)
        if result.get("status") == "missing":
            safe_print(f"\n=== {name} ===")
            safe_print("Document not found.")
            report.append(result)
            continue

        safe_print(f"\n=== {result['document']} ===")
        safe_print(f"Current type={result.get('current_type')} date={result.get('current_date')}")

        if result.get("status") == "ok":
            parsed = result["profile"]
            safe_print(json.dumps(parsed, ensure_ascii=False, indent=2))
            report.append(result)
        else:
            safe_print("Profile generation did not return valid JSON.")
            safe_print(str(result.get("raw_response") or ""))
            report.append(result)

    if args.write_report:
        report_path = Path(args.write_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        safe_print(f"\nWrote report: {report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
