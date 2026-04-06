# Session Handoff 2026-04-04

This is the checkpoint for the latest prototype round.

## What We Did

- Ran a fresh health check of the main app:
  - `./scripts/preflight.ps1` passed with only the existing `.env` and local `Qdrant` warnings
  - `py -3 -m compileall backend` stayed green
- Revisited quantization strategy:
  - good fit for Ollama chat-model runtime
  - not the main lever for OCR, extraction, or retrieval-tool selection
- Installed and tested `marker-pdf`
- Installed and tested direct `surya-ocr`

## Marker Result

- `Marker` is not a good fit for the local baseline.
- It downgraded shared dependencies like `Pillow` and `pypdfium2`.
- Single-document tests timed out without producing useful output in time.
- It left background processes behind after timeout.
- We removed `marker-pdf` and restored key shared packages afterward.

## Surya Result

- Direct `Surya` is more promising than `Marker`.
- First run required a very large model download.
- On `ARCHITECTURE.pdf`, it produced strong OCR text with only small issues like `AI` becoming `Al`.
- On `Dokument_2023-10-31_180442.pdf`, it produced fairly rich OCR output and looked meaningfully usable.
- It still wants dependency versions that conflict with parts of the current prototype stack, so it should remain isolated for now.

## Current Best Prototype Direction

- Keep `OCRmyPDF` as the strongest OCR winner already integrated selectively.
- Keep `GLiNER` as the strongest enrich/entity winner.
- Keep `Surya` as a promising OCR/layout candidate, but not yet part of the normal local baseline.
- Keep `Docling`, `Unstructured`, document profiles, and rerankers in prototype-only status.
- Drop `Marker` from near-term consideration.

## Best Next Step

If we continue next session, the best move is:

1. Decide whether to benchmark `Surya` in a more isolated way:
   - separate venv
   - Docker/WSL
   - server-like benchmark lane
2. If yes, build a proper repeatable `Surya` compare script and OCR suite.
3. If no, focus back on product-facing wins with the current winners:
   - better answer synthesis
   - richer metadata usage
   - cleaner retrieval behavior

## Later Same-Day Update

- Wrote down the OCR decision explicitly in `Docs/ocr-decision.md`.
- Split the `Unstructured` structure evaluation into:
  - mixed suite
  - PDF-focused suite
  - structured-text business suite
- Latest measured `Unstructured` result:
  - mixed suite: `1 improved / 4 regressed`
  - PDF-focused suite: `3 improved / 2 regressed`
  - structured-text suite: `0 improved / 3 regressed`
- Best reading of that result:
  - do not treat `Unstructured` as a global replacement
  - keep it alive as a selective PDF-structure candidate
  - keep the in-house parser for structured `.txt` business documents

## Code And Config Intake Update

- The main backend now treats a much broader range of code and config files as first-class text-like documents.
- This now includes common code extensions such as `ts`, `tsx`, `js`, `jsx`, `py`, `java`, `cs`, `go`, `rs`, `sql`, and `ps1`.
- It also includes common config extensions such as `yml`, `yaml`, `toml`, `ini`, `cfg`, `conf`, `env`, `properties`, and `xml`.
- A synthetic SharePoint-style TypeScript fixture was added and now passes retrieval/eval coverage for code-oriented document search.

## Office And SharePoint-Style Intake Update

- The main backend now supports `docx`, `xlsx`, and `pptx` as first-class inputs in the normal product path.
- `docx` uses native parsing through `python-docx`.
- `xlsx` uses native parsing through `openpyxl` and now extracts rows in a more semantic way so retrieval can answer against sheet content instead of only a flat text dump.
- `pptx` uses native parsing through `python-pptx` and now extracts slide-aware content so retrieval can answer against specific presentation topics.
- Phrase matching for content questions was relaxed so Office documents are not unfairly penalized when the exact long phrase is not present as one contiguous string.
- The synthetic SharePoint-style Office and code suite now goes `15/15`.

## Current Mainline Decisions

- OCR mainline:
  - primary: `OCRmyPDF`
  - fallback: `Tesseract`
- Enrichment mainline:
  - cautious `GLiNER` usage is the strongest enrich path so far
- Office/document parsing mainline:
  - `python-docx`
  - `openpyxl`
  - `python-pptx`

## Best Next Step

If we continue next session, the most natural move is:

1. Start designing the connector/routing layer for external sources like SharePoint and Google Workspace.
2. Keep the routing generic:
   - connector fetch/export
   - file-type routing
   - ingestion
   - retrieval
3. Keep prototyping parsing tools separately, but only pull them into the product if they clearly beat the current mainline stack.

## Connector Routing Update

- A first generic connector-ingest foundation now exists.
- A first connector manifest layer now also exists.
- Document metadata can now preserve:
  - source origin
  - provider
  - source URI
  - source container
  - source last-modified timestamp
- The main document service can now import externally sourced files into the same storage and processing path as normal uploads.
- A dedicated connector-ingest service now exists as the generic entrypoint for future SharePoint, Google Workspace, OneDrive, or local-folder sync lanes.
- A connector registry and first `/connectors` API surface now exist so future connectors can be defined before sync workers are implemented.
- A first mock/local sync lane now also exists through `/connectors/{id}/sync-local`, so a SharePoint-style library can be simulated from a local folder before we wire in real provider auth.
- A generic `/connectors/{id}/sync` route now exists and dispatches by provider, with SharePoint as the first named provider in that dispatch layer.
- A first Graph-backed SharePoint prototype now also exists behind that provider layer, using client credentials and `drive_id`/`folder_path` manifest settings when real SharePoint testing begins.
- A first Google Drive / Workspace provider now also exists behind that same connector layer.
- The Google provider supports:
  - mock/manual/local mode through the same local-folder prototype lane
  - live Drive sync through OAuth refresh-token credentials
  - recursive listing inside Drive folders
  - native export of Google Docs/Sheets/Slides into `docx`, `xlsx`, and `pptx`
- Current required Google env values:
  - `GOOGLE_DRIVE_CLIENT_ID`
  - `GOOGLE_DRIVE_CLIENT_SECRET`
  - `GOOGLE_DRIVE_REFRESH_TOKEN`
- Current optional Google provider settings:
  - `folder_id`
  - `drive_id`
- Connector design is now documented in `Docs/connector-routing.md`.

## Best Next Step

If we continue after this checkpoint, the most natural move is:

1. Decide whether the first live connector test should be Google Drive or SharePoint, depending on which credentials are easiest to use next.
2. Keep the provider-specific part narrow:
   - authenticate
   - list
   - export/download
   - pass files into connector-ingest

## Security Update

- A first security risk register now exists in `Docs/security-risk-register.md`.
- The current honest assessment is:
  - good internal MVP
  - not yet ready for security-classified enterprise document handling
- The biggest current gaps are:
  - no authentication
  - no authorization
  - no tenant isolation
  - no encryption-at-rest strategy
  - admin-capable routes that are too open for hardened deployments
- Recommended next security move:
  - design `safe mode` / hardened mode
  - then implement auth and admin-route protection on top of it
