# Installation Plan

This document defines the current manual installation baseline for the project and the order dependencies should be installed in before we automate more of the setup.

The goal is simple:

- keep local setup repeatable
- avoid hidden machine-specific assumptions
- make future automation easier to build safely

For the first real server-bootstrap direction, see [Linux Installer V1](./linux-installer-v1.md).

## Scope

This is not a full inventory of everything installed on a developer machine.

This is the project installation plan for:

- Windows development
- Ubuntu 24 deployment
- shared runtime dependencies used by the app

## Installation Principles

- Install platform dependencies before app dependencies.
- Reuse shared services where possible instead of duplicating them per deploy.
- Keep OCR, vector storage, and model runtime explicit so failures are easier to debug.
- Prefer a small number of focused setup steps over one large script that is hard to trust.
- Keep a clear line between prototype tooling and hardened production tooling.
- Plan for a future `safe mode` where stricter security defaults are applied automatically.

## Required Programs

### Windows Development

- `Git`
- `Python 3.13`
- `Node.js` and `npm`
- `Docker Desktop`
- `Tesseract OCR`
- `Poppler` only if we want to run the local `Unstructured` PDF prototype lane

### Shared Runtime Services

- `Ollama`
- `Qdrant`

### Connector Prototype Environment

Only needed when we move from mock/local connectors to real provider APIs:

- `SHAREPOINT_TENANT_ID`
- `SHAREPOINT_CLIENT_ID`
- `SHAREPOINT_CLIENT_SECRET`
- `GOOGLE_DRIVE_CLIENT_ID`
- `GOOGLE_DRIVE_CLIENT_SECRET`
- `GOOGLE_DRIVE_REFRESH_TOKEN`

### Security Baseline We Still Need

These are not fully implemented yet, but they should be treated as planned baseline requirements for sensitive company deployments:

- stronger authentication beyond the current local admin session model
- role-based access control beyond the current admin-only foundation
- encrypted storage or encrypted host volumes
- encrypted backup/export path
- audit logging
- stricter upload and request limits
- `safe mode` / hardened runtime profile

### Python Packages

Installed from `backend/requirements.txt`, including:

- `fastapi`
- `uvicorn`
- `qdrant-client`
- `python-docx`
- `openpyxl`
- `python-pptx`
- `pypdf`
- `PyMuPDF`
- `pytesseract`
- `Pillow`

Current first-class text-like file coverage in the main backend now includes:

- notes and plain text
- markdown
- json and line-delimited json
- csv and tsv
- code files such as `py`, `ts`, `tsx`, `js`, `jsx`, `java`, `cs`, `go`, `rs`, `sql`, `ps1`
- config files such as `yml`, `yaml`, `toml`, `ini`, `cfg`, `conf`, `env`, `properties`, `xml`

Current first-class Office-style coverage in the main backend now includes:

- `docx`
- `xlsx`
- `pptx`

Current product-path OCR and extraction decisions:

- primary scanned-PDF OCR: `OCRmyPDF` through Docker
- OCR fallback: `Tesseract`
- native Office parsing:
  - `python-docx` for `docx`
  - `openpyxl` for `xlsx`
  - `python-pptx` for `pptx`
- entity enrichment winner so far: `GLiNER`

Current product-path routing intent:

- scanned or weak PDFs: `OCRmyPDF` first, `Tesseract` fallback
- images: existing OCR path
- Word documents: native parser path
- spreadsheets: native parser path with row-aware chunking
- presentations: native parser path with slide-aware chunking
- code and config files: direct text-like parsing
- future connectors should export or fetch files into this same routing path instead of bypassing it

Current live connector requirements by provider:

- SharePoint:
  - `SHAREPOINT_TENANT_ID`
  - `SHAREPOINT_CLIENT_ID`
  - `SHAREPOINT_CLIENT_SECRET`
- Google Drive / Workspace:
  - `GOOGLE_DRIVE_CLIENT_ID`
  - `GOOGLE_DRIVE_CLIENT_SECRET`
  - `GOOGLE_DRIVE_REFRESH_TOKEN`

Current Google Drive prototype behavior:

- normal Drive files are downloaded directly
- native Google Docs are exported to `docx`
- native Google Sheets are exported to `xlsx`
- native Google Slides are exported to `pptx`
- the same downstream parsing, OCR, chunking, and retrieval path is reused after export

Current security/runtime behavior in the product path:

- a first admin auth layer now exists for sensitive routes
- `SAFE_MODE` can block risky operations such as cleanup and backup import/export
- document visibility can now be set to `hidden` so non-admin views and retrieval do not expose that content
- current auth/safe-mode toggles are still environment-driven and should be treated as prototype-safe rather than final enterprise UX

### Optional Local Prototyping Stack

Used only when we are testing alternative ingestion and OCR pipelines locally before adoption into the main app:

- `unstructured[pdf]`
- `unstructured-inference`
- `Poppler`
- `gliner`
- `paddleocr`
- `paddlepaddle`
- `easyocr`
- `ocrmypdf`
- `docling`
- `marker-pdf`
- `surya-ocr`
- `sentence-transformers`
- `json-repair`
- local Ollama runtime for document-profile prototyping

Current prototype-only status summary:

- keep testing selectively:
  - `Unstructured`
  - `Docling`
  - `Surya`
  - local Ollama document profiles
  - external rerankers
- not part of the main path now:
  - `Marker`
  - `PaddleOCR`
  - `EasyOCR` as a replacement

These are not part of the production baseline yet. They are currently a local evaluation track.

### Frontend Packages

Installed from `frontend/package.json`, including:

- `next`
- `react`
- `eslint`

## Current Installation Order

### Windows Dev Order

1. Install `Git`.
2. Install `Python 3.13`.
3. Install `Node.js` and `npm`.
4. Install `Docker Desktop`.
5. Install `Tesseract OCR`.
6. Install `Ollama` locally, or prepare the remote Ollama host.
7. Clone the repo.
8. Copy `.env.example` to `.env`.
9. Install backend Python packages with `py -3 -m pip install -r backend/requirements.txt`.
10. Install frontend packages with `npm install` in `frontend/`.
11. Build the OCR helper image once with `docker build -t local-ai-ocrmypdf:latest -f infra/ocrmypdf/Dockerfile .`.
12. Start infra with `./scripts/dev-up.ps1`.
13. Start backend with `py -3 -m uvicorn main:app --reload` from `backend/`.
14. Start frontend with `npm run dev` from `frontend/`.

Optional but now recommended when testing security/admin behavior locally:

15. Set these in `/.env` before starting the backend if you want admin auth enabled:
   - `AUTH_ENABLED=true`
   - `ADMIN_PASSWORD_HASH=...`
   - `ADMIN_SESSION_SECRET=...`
   - `APP_SECRETS_KEY=...`
16. Optionally enable safer local behavior with:
   - `SAFE_MODE=true`

Optional local prototype order after the baseline is working:

17. Install `unstructured[pdf]` in the active Python environment.
18. Install `unstructured-inference`.
19. Install `Poppler`.
20. Install `gliner`.
21. Run `./scripts/eval/unstructured-compare.ps1` against a few representative files.
22. Run `./scripts/eval/unstructured-structure.ps1` against the representative structure suite.
23. Run `./scripts/eval/gliner-compare.ps1` against a few representative files.
24. Run `./scripts/eval/document-profile.ps1` against a few representative files.
25. Run `./scripts/eval/reranker-compare.ps1` against a representative eval suite.

### Ubuntu Deploy Order

1. Install `Git`.
2. Install `Docker Engine` and Docker Compose support.
3. Clone the repo.
4. Copy `.env.ubuntu.example` to `.env.ubuntu`.
5. Set runtime values such as `OLLAMA_BASE_URL`, `NEXT_PUBLIC_API_BASE_URL`, and ports.
6. Run `./scripts/deploy/ubuntu/install.sh`.
7. Start the deployment stack with `./scripts/deploy/ubuntu/start.sh`.
8. Verify services with `./scripts/deploy/ubuntu/status.sh`.

This is still the manual deployment path.
The target next step is to wrap this in a first-install Linux bootstrap flow for a blank server.

That installer-oriented phase split now exists at script level:

1. `./scripts/deploy/ubuntu/bootstrap.sh`
2. `./scripts/deploy/ubuntu/configure.sh`
3. `./scripts/deploy/ubuntu/deploy.sh`
4. `./scripts/deploy/ubuntu/verify.sh`

The first GitHub-delivered bootstrap path now also exists:

1. download `scripts/deploy/bootstrap-from-web.sh` from the repo
2. run it on the blank Ubuntu server
3. let it fetch the repo payload and hand off to `scripts/deploy/ubuntu/installer.sh`

If the repo remains private, the bootstrap flow currently expects a GitHub token in an env var such as `GITHUB_TOKEN`.

## Dependency Notes

### Ollama

- The backend talks to the Ollama API endpoint, not a web UI port.
- Example correct API URL: `http://192.168.1.105:11434`
- If Ollama is remote, `OLLAMA_BASE_URL` must point to that host before backend startup.

### Qdrant

- Qdrant is currently expected to run through the project Docker setup.
- Local Windows development starts it with `./scripts/dev-up.ps1`.
- Ubuntu deployment starts it with the deployment compose stack.

### Tesseract OCR

- OCR is now used for scanned PDFs and common image formats.
- Current default OCR language should support mixed English and Swedish documents.
- Extra language packs should live in a project-controlled OCR data directory where possible.
- Handwritten text is still best-effort even with OCR enabled.

### OCRmyPDF

- `OCRmyPDF` is now part of the main product path for weak or scanned PDFs.
- It currently runs through Docker and uses the helper image defined in `infra/ocrmypdf/Dockerfile`.
- The helper image should be available locally as `local-ai-ocrmypdf:latest`.
- This is currently our primary OCR engine for scanned PDFs.

### Office Parsing

- `docx`, `xlsx`, and `pptx` are now part of the main backend path, not just prototypes.
- `docx` currently performs well enough for normal retrieval.
- `xlsx` now uses row-aware extraction and chunking.
- `pptx` now uses slide-aware extraction and chunking.
- The current synthetic SharePoint-style Office and code suite is green at `15/15`.

### Unstructured Prototype

- The local prototype currently depends on both `unstructured[pdf]` and `unstructured-inference`.
- PDF comparison quality improves when `Poppler` is installed and reachable.
- The prototype script now tries to auto-detect WinGet installs of `Poppler` and common Windows installs of `Tesseract`.
- A representative structure suite now exists at `backend/evals/unstructured_structure_cases.json` and can be run with `./scripts/eval/unstructured-structure.ps1`.
- A PDF-focused suite now exists at `backend/evals/unstructured_pdf_structure_cases.json`.
- A structured-text business suite now exists at `backend/evals/unstructured_text_structure_cases.json`.
- Current measured result:
  - mixed suite: `1 improved / 4 regressed`
  - PDF-focused suite: `3 improved / 2 regressed`
  - structured-text suite: `0 improved / 3 regressed`
- Current local finding: this path looks better for some PDFs than for structured `.txt` business documents, so any future runtime use should likely be selective rather than global.
- This path is for evaluation only until we decide whether to adopt it into the main backend pipeline.

### GLiNER Prototype

- The local prototype uses `gliner` for broader, label-driven entity extraction.
- It is useful for testing whether we should replace or enrich our current company/entity heuristics with a more general NER layer.
- The current prototype script is `./scripts/eval/gliner-compare.ps1`.
- `GLiNER` is now the strongest enrichment candidate we have tested and parts of that path are already being used cautiously in the main ingestion flow.
- We should still treat broader rollout and backfill decisions as explicit, not automatic.

### Document Profile Prototype

- The local prototype uses the configured Ollama chat model to produce structured JSON profiles for selected documents.
- It is useful for testing whether LLM-assisted summaries, themes, search clues, and entities are more generally useful than hand-written heuristics alone.
- The current prototype script is `./scripts/eval/document-profile.ps1`.
- The current validation script is `./scripts/eval/document-profile-eval.ps1`.
- `json-repair` is now part of the local prototype path because it makes malformed LLM JSON far more usable during evaluation.
- This path is evaluation-only until we decide whether document profiling belongs in the main ingest pipeline.

### Reranker Prototype

- The local prototype uses `sentence-transformers` with a CrossEncoder reranker.
- It is useful for testing whether external reranking improves document and chunk ordering over our current scoring logic.
- The current prototype script is `./scripts/eval/reranker-compare.ps1`.
- This path is evaluation-only until we decide whether reranking belongs in the main retrieval flow.

### OCR Engine Prototype

- The local prototype track now includes `PaddleOCR`, `EasyOCR`, and `OCRmyPDF` for OCR-engine comparison.
- `PaddleOCR` currently installs successfully but fails during inference on both our local Windows CPU environment and the first Linux Docker benchmark, so it should stay in prototype-only status until we can find a stable runtime combination.
- `EasyOCR` currently runs locally and can be benchmarked with `./scripts/eval/easyocr-compare.ps1`.
- `OCRmyPDF` is now benchmarked in Docker with `./scripts/eval/ocrmypdf-docker.ps1` so scanned-PDF preprocessing can be tested in a Linux-like runtime without changing the main app yet.
- The first `OCRmyPDF` benchmark run passed both representative OCR cases and improved one Swedish term-match compared with the current OCR output, so it currently looks like the strongest alternative OCR building block we have tested.
- The broader mixed OCR suite also kept `OCRmyPDF` green across scanned, receipt, reminder, and invoice-style PDFs, which makes it a better near-term candidate than `EasyOCR` for selective adoption.
- The main backend can now selectively call `OCRmyPDF` through Docker for weak/scanned PDFs, using the helper image defined in `infra/ocrmypdf/Dockerfile`.
- This path is evaluation-only until we decide whether an alternative OCR engine belongs in the main OCR pipeline.

### Docling Prototype

- The local prototype track now includes `docling` for PDF-focused structure and extraction evaluation.
- The comparison entrypoint is `./scripts/eval/docling-compare.ps1`, using `backend/evals/docling_structure_cases.json`.
- Current local finding: `Docling` looks promising on clean PDFs such as architecture, roadmap, and current-feature style documents, but it is much heavier than our current stack and becomes unstable on larger manuals and some OCR-heavy PDFs on the present Windows development machine.
- Installing `docling` also introduces a local `typer` version mismatch warning in the current prototype environment, so it should stay prototype-only for now.
- This path is for evaluation only until we decide whether there is a selective server-side use case where its structure gains justify the runtime cost.

### Marker Prototype

- `marker-pdf` was tested as a local prototype candidate.
- Current finding: it is not a good fit for the local baseline. It changed shared dependencies, timed out on simple single-document runs, and left background processes behind after timeout.
- It should not be pulled into the main application path in its current form.

### Surya Prototype

- `surya-ocr` has now been tested directly, without `Marker` wrapped around it.
- Current finding: OCR quality looks more promising than `Marker`, especially on OCR-heavy pages, but the first-run model download is large and it also wants dependency versions that conflict with parts of the current prototype environment.
- If we keep evaluating it, it should ideally live in a more isolated prototype environment or a server-like benchmark lane rather than the everyday Windows dev baseline.

## What Should Later Be Automated

### Highest Priority

- environment preflight checks
- dependency presence checks
- `.env` bootstrap and validation
- blank-server Linux bootstrap flow
- backend dependency install
- frontend dependency install
- Tesseract presence and language-pack checks
- Ollama connectivity check
- Qdrant connectivity check

Status:

- a first local preflight script now exists at `./scripts/preflight.ps1`
- next step is to expand it into a fuller bootstrap and validation flow

### After That

- one-command Windows dev bootstrap
- one-command Ubuntu install validation
- optional OCR language-pack setup
- optional local Ollama model pull flow
- health checks after install
- safe-mode preflight validation
- security hardening checks for production deployment
- connector secret/token validation that does not rely on exposing credentials in docs or manual chat copy/paste

## What Should Stay Explicit

- destructive cleanup
- upload reset
- Qdrant storage reset
- switching between local and remote Ollama hosts
- OCR language changes

These should stay visible and deliberate even after more automation exists.

## Verification Checklist

After setup, verify:

- frontend opens on `http://localhost:3000`
- backend responds on `http://127.0.0.1:8000/status`
- `/models` works
- `Qdrant` is reachable
- document upload works
- OCR works for a scanned PDF or image file
- Office-style files can be uploaded and answered against:
  - `docx`
  - `xlsx`
  - `pptx`

## Future Automation Goal

The long-term target is:

- small install scripts
- clear validation output
- safe retries
- no giant bootstrap script that hides too much state

That matches the rest of the project rule set: modular scripts, explicit cleanup boundaries, and predictable runtime behavior.
