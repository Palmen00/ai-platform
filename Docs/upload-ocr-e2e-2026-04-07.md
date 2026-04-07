# Upload And OCR E2E 2026-04-07

## Summary

We ran a broad end-to-end upload and OCR validation against the live server at `192.168.1.105`.

The test covered:

- upload acceptance
- background processing
- indexing
- preview extraction
- OCR for scanned inputs
- chat retrieval against the uploaded document
- negative upload rejection for an unsupported file type

Final result:

- `11/11` representative file cases passed
- OCR passed for both image and scanned PDF
- unsupported `.exe` upload was rejected correctly

## Test Script

- [scripts/tests/run_upload_ocr_e2e.py](../scripts/tests/run_upload_ocr_e2e.py)

The script generates fixtures, uploads them, waits for processing, checks preview text, asks the assistant document-scoped questions, and writes JSON plus Markdown reports under `temp/upload-ocr-test/`.

## Covered File Types

- `txt`
- `md`
- `json`
- `csv`
- `xml`
- `py`
- `docx`
- `xlsx`
- `pptx`
- `png` with OCR
- `pdf` with OCR

## Reports

The script writes timestamped JSON and Markdown reports under:

- `temp/upload-ocr-test/`

The validated green run for this pass was:

- `upload-ocr-report-20260407-163133.md`
- `upload-ocr-report-20260407-163133.json`

## What Failed First

The first wide run exposed two real classes of issues:

1. The test script initially picked the embedding model for `/chat` instead of a chat-capable model.
2. Retrieval for structured files was too strict, especially for spreadsheet-like short terms such as `Q2`, and when a document was already explicitly selected.

## Fixes Applied

Retrieval was improved in:

- [backend/app/services/documents.py](../backend/app/services/documents.py)
- [backend/app/services/retrieval.py](../backend/app/services/retrieval.py)

Main changes:

- query term extraction now keeps compact alphanumeric terms like `Q2`
- source matching now considers section titles together with excerpts
- document-scoped retrieval no longer discards all selected sources too aggressively when the user already limited the query to one document

## Current Assessment

Upload, extraction, OCR, indexing, and document-grounded chat are in a good state for the covered formats.

This is not an exhaustive test of every possible office or media format, but it is a strong regression baseline for the current product surface.

## Connector Note

Google Drive was not tested in this pass because the server currently has no Drive connector configured and no Google Drive credentials set in `.env.ubuntu`.

The next connector-focused pass should cover:

- Google Drive browse
- Google Drive preview sync
- Google Drive real sync
- permission and source-metadata verification on imported files
