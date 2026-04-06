# Scripts

PowerShell scripts are split by responsibility so cleanup, development, and setup do not live inside one large file.

## Common Commands

- `./scripts/dev-up.ps1`
- `./scripts/dev-down.ps1`
- `./scripts/dev/status.ps1`
- `./scripts/dev/logs.ps1`
- `./scripts/preflight.ps1`
- `./scripts/eval/retrieval.ps1`
- `./scripts/clean-light.ps1`
- `./scripts/clean-deep.ps1`

## Eval Commands

- `./scripts/eval/retrieval.ps1`
- `./scripts/eval/retrieval.ps1 -WithReplies`
- `./scripts/eval/retrieval.ps1 -WriteReport temp/retrieval-eval-report.json`
- `./scripts/eval/retrieval.ps1 -Suite backend/evals/retrieval_hard_cases.json`
- `./scripts/eval/retrieval.ps1 -Suite backend/evals/reply_quality_cases.json -WithReplies`
- `./scripts/eval/retrieval.ps1 -Suite backend/evals/document_coverage_cases.json -WithReplies`
- `./scripts/eval/synthetic.ps1`
- `py -3 scripts/eval/generate_office_fixtures.py`
- `./scripts/eval/retrieval.ps1 -Suite backend/evals/synthetic_signal_cases.json -WithReplies`
- `./scripts/eval/unstructured-compare.ps1`
- `./scripts/eval/unstructured-compare.ps1 "ARCHITECTURE.pdf" "Dokument_2023-10-31_180442.pdf"`
- `./scripts/eval/unstructured-structure.ps1`
- `./scripts/eval/unstructured-structure.ps1 -WriteReport temp/unstructured-structure-report.json`
- `./scripts/eval/unstructured-structure.ps1 -Suite backend/evals/unstructured_pdf_structure_cases.json -WriteReport temp/unstructured-pdf-structure-report.json`
- `./scripts/eval/unstructured-structure.ps1 -Suite backend/evals/unstructured_text_structure_cases.json -WriteReport temp/unstructured-text-structure-report.json`
- `./scripts/eval/document-profile.ps1`
- `./scripts/eval/document-profile.ps1 -WriteReport temp/document-profile-report.json`
- `./scripts/eval/document-profile-eval.ps1`
- `./scripts/eval/document-profile-eval.ps1 -WriteReport temp/document-profile-eval-report.json`
- `./scripts/eval/easyocr-compare.ps1`
- `./scripts/eval/easyocr-compare.ps1 -WriteReport temp/easyocr-compare-report.json`
- `./scripts/eval/easyocr-compare.ps1 -Suite backend/evals/ocr_engine_extended_cases.json -WriteReport temp/easyocr-extended-report.json`
- `./scripts/eval/ocrmypdf-docker.ps1`
- `./scripts/eval/ocrmypdf-docker.ps1 -WriteReport temp/ocrmypdf-docker-report.json`
- `./scripts/eval/ocrmypdf-docker.ps1 -Suite backend/evals/ocr_engine_extended_cases.json -WriteReport temp/ocrmypdf-extended-report.json`
- `./scripts/eval/paddleocr-docker.ps1`
- `./scripts/eval/paddleocr-docker.ps1 -WriteReport temp/paddleocr-docker-report.json`
- `./scripts/eval/docling-compare.ps1`
- `./scripts/eval/docling-compare.ps1 -WriteReport temp/docling-compare-report.json`
- `./scripts/eval/gliner-compare.ps1`
- `./scripts/eval/gliner-compare.ps1 "ARCHITECTURE.pdf" "Salgsfaktura 512376.pdf"`
- `./scripts/eval/reranker-compare.ps1`
- `./scripts/eval/reranker-compare.ps1 -Suite backend/evals/document_coverage_cases.json`

The baseline suite lives in `backend/evals/retrieval_baseline.json`.
Harder OCR and disambiguation checks live in `backend/evals/retrieval_hard_cases.json`.
Reply-quality checks live in `backend/evals/reply_quality_cases.json`.
Broader document coverage checks live in `backend/evals/document_coverage_cases.json`.
Synthetic business-style checks live in `backend/evals/synthetic_signal_cases.json`.
`py -3 scripts/eval/generate_office_fixtures.py` regenerates the synthetic `docx`, `xlsx`, and `pptx` fixtures used to test SharePoint-style Office intake.
Representative OCR engine checks live in `backend/evals/ocr_engine_cases.json`.
Broader mixed OCR checks live in `backend/evals/ocr_engine_extended_cases.json`.
`./scripts/eval/unstructured-compare.ps1` runs a local comparison between the current document pipeline and an Unstructured prototype against selected uploaded files.
`./scripts/eval/unstructured-structure.ps1` scores current vs `Unstructured` title and section extraction over a representative eval suite before we decide whether to adopt a new partitioning path.
`backend/evals/unstructured_pdf_structure_cases.json` isolates the PDF-heavy cases where `Unstructured` has the best chance to help.
`backend/evals/unstructured_text_structure_cases.json` isolates the structured `.txt` business cases where our in-house parser currently performs much better.
`./scripts/eval/document-profile.ps1` asks the local Ollama model for structured JSON document profiles so we can evaluate LLM-assisted metadata enrichment before integrating it into ingest.
`./scripts/eval/document-profile-eval.ps1` validates those local Ollama document profiles against expected type, entity, date, and search-clue signals.
`./scripts/eval/easyocr-compare.ps1` compares EasyOCR against the current OCR path on representative scanned documents, including timing and expected-term hits.
`./scripts/eval/ocrmypdf-docker.ps1` runs the same OCR suite inside a Linux Docker container using OCRmyPDF as a preprocessing OCR path.
`./scripts/eval/paddleocr-docker.ps1` runs the same OCR suite inside a Linux Docker container so PaddleOCR can be tested in a more server-like environment than local Windows CPU inference.
`./scripts/eval/docling-compare.ps1` benchmarks the current PDF pipeline, `Unstructured`, and `Docling` over a representative PDF-structure suite before any Docling adoption decision.
`./scripts/eval/gliner-compare.ps1` runs a local comparison between the current entity/signal pipeline and a GLiNER prototype against selected uploaded files.
`./scripts/eval/reranker-compare.ps1` runs a local comparison between the current ranking and a CrossEncoder reranker over an eval suite.

## Ubuntu Deploy Commands

Use these on the Ubuntu deployment host:

- `./scripts/deploy/ubuntu/install.sh`
- `./scripts/deploy/ubuntu/start.sh`
- `./scripts/deploy/ubuntu/stop.sh`
- `./scripts/deploy/ubuntu/status.sh`
- `./scripts/deploy/ubuntu/logs.sh backend`
- `./scripts/deploy/ubuntu/update.sh`
- `./scripts/deploy/ubuntu/cleanup.sh`

## Destructive Commands

These commands require `-Force` and are intentionally separate from regular cleanup:

- `./scripts/cleanup/reset-uploads.ps1 -Force`
- `./scripts/cleanup/reset-qdrant.ps1 -Force`
