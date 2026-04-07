# Local AI OS

Self-hosted AI platform with:
- Ollama (models)
- Qdrant (vector DB)
- FastAPI backend
- Next.js frontend
- Local document upload management

## Documentation

Primary project documentation now lives in Markdown under [Docs/README.md](Docs/README.md).

The PDF files in `Docs/` are kept as legacy source material, but the `.md` files are the versions to maintain going forward.

## Environment Model

- Windows is the primary development environment
- Ubuntu 24 is the primary deployment target
- Local Windows usage should stay lightweight and reuse shared services like Ollama where possible

## Setup

1. Copy `.env.example` to `.env` and adjust values if needed.
2. Install backend dependencies with `py -3 -m pip install -r backend/requirements.txt`.
3. Install frontend dependencies with `npm install` in `frontend/`.
4. Start infrastructure with `./scripts/dev-up.ps1`.
5. Run the backend locally with `py -3 -m uvicorn main:app --reload` from `backend/`.
6. Run the frontend locally with `npm run dev` from `frontend/`.

If you want a gentler local dev mode on Windows, use:

```powershell
./scripts/dev/run-backend.ps1 -Reload
```

That starts the backend in a separate PowerShell window with lower process priority and `LOW_IMPACT_MODE=true`, which reduces local CPU pressure by disabling GLiNER enrichment and using smaller embedding batches. For production or server-like runs, switch `LOW_IMPACT_MODE=false`.

For admin protection and a stricter runtime profile, these env values are now available:

- `AUTH_ENABLED=true`
- `ADMIN_USERNAME=Admin`
- `ADMIN_PASSWORD_HASH=...`
- `ADMIN_SESSION_SECRET=...`
- `APP_SECRETS_KEY=...`
- `ADMIN_SESSION_TTL_HOURS=12`
- `SAFE_MODE=true`
- `APP_TIMEZONE=Europe/Stockholm`
- `ASSISTANT_INTELLIGENCE_ENABLED=true`
- `ASSISTANT_BASE_PACKS=base,local-ai-os`
- `ASSISTANT_OPTIONAL_PACKS=code,reference`

When `AUTH_ENABLED` is active and fully configured, `Settings`, `Connectors`, logs, runtime changes, cleanup, and backup import/export require admin sign-in from the UI. `SAFE_MODE` additionally blocks higher-risk operations such as cleanup, backup import/export, runtime setting changes, and manual connector imports.

Fresh installs can also enable a small built-in assistant intelligence layer. It injects local date, time, weekday, and ISO week into prompts and adds compact starter prompt packs for general answering, Local AI OS product guidance, coding help, and light reference behavior, so the assistant feels more useful even before any documents are uploaded.

Admin sessions now use an `HttpOnly` cookie instead of browser storage. New installs should prefer `ADMIN_PASSWORD_HASH` over cleartext `ADMIN_PASSWORD`, and `.env.ubuntu` is now written with `chmod 600` by the Ubuntu configure phase. The installer/bootstrap flow now also writes `ADMIN_USERNAME`, so the first bootstrap admin can be named during setup instead of being fixed in code.

Optional OCR support for scanned PDFs and image files:

- Install backend OCR dependencies with `py -3 -m pip install -r backend/requirements.txt`
- Install the Tesseract OCR engine on the machine
- Set `TESSERACT_CMD` in `.env` on Windows if `tesseract.exe` is not already on `PATH`
- A selective `OCRmyPDF` preprocessing path is now built into the backend for weak/scanned PDFs, using Docker by default
- The first time that OCRmyPDF path runs, the backend can auto-build the helper image from `infra/ocrmypdf/Dockerfile`
- OCR can now be used for scanned/image-first inputs such as `.jpg`, `.jpeg`, `.png`, `.bmp`, `.tif`, `.tiff`, and `.webp`
- Swedish OCR is supported through `OCR_LANGUAGE=eng+swe`; install extra Tesseract language packs if you want to expand beyond that
- The OCR pipeline now tries multiple page-segmentation modes and image variants before choosing the strongest result
- OCR metadata now records which engine was used so `Knowledge` can show whether a PDF was read through native text, `Tesseract`, or `OCRmyPDF`
- GLiNER can now be enabled as an entity-enrichment layer during document processing to improve company, organization, project, and contract-style signal extraction
- GLiNER enrichment is still a cautious adoption path: it currently strengthens document entities during processing while the older heuristic extraction remains as fallback
- Existing documents are not bulk-refreshed with GLiNER by default; reprocess selected documents if you want the new entity layer to be applied immediately

## Scripts

- `./scripts/dev-up.ps1`: Ensure project directories exist and start Docker services from `infra/`
- `./scripts/dev-down.ps1`: Stop Docker services
- `./scripts/dev/status.ps1`: Show Docker service status
- `./scripts/dev/logs.ps1 backend`: Follow service logs
- `./scripts/dev/ensure-qdrant.ps1`: Ensure the local Qdrant container is running and healthy
- `./scripts/dev/run-backend.ps1 -Reload`: Start the backend in a separate PowerShell window with lower priority and optional low-impact mode
- `./scripts/dev/check-network.ps1`: Show top CPU processes, top external connection owners, and AI-stack network activity
- `./scripts/preflight.ps1`: Check local tooling, backend imports, OCR support, and service reachability
- `./scripts/eval/retrieval.ps1`: Run the baseline retrieval eval suite
- `./scripts/eval/retrieval.ps1 -WithReplies`: Run retrieval plus model-answer checks
- `./scripts/eval/retrieval.ps1 -Suite backend/evals/retrieval_hard_cases.json`: Run harder OCR/disambiguation retrieval checks
- `./scripts/eval/retrieval.ps1 -Suite backend/evals/reply_quality_cases.json -WithReplies`: Run reply-quality checks for natural document and OCR answers
- `./scripts/eval/retrieval.ps1 -Suite backend/evals/document_coverage_cases.json -WithReplies`: Run broader document coverage checks across the current uploaded-document mix
- `py -3 scripts/tests/run_upload_ocr_e2e.py --base-url http://<server>:8000`: Run the broad upload/OCR/document-chat end-to-end validation suite
- `./scripts/eval/unstructured-compare.ps1`: Compare the current ingestion pipeline with a local Unstructured prototype
- `./scripts/eval/gliner-compare.ps1`: Compare the current entity pipeline with a local GLiNER prototype
- `./scripts/deploy/ubuntu/install.sh`: Run the installer-oriented Ubuntu flow end-to-end
- `./scripts/deploy/ubuntu/installer.sh`: Top-level wrapper for `bootstrap`, `configure`, `deploy`, and `verify`
- `./scripts/deploy/bootstrap-from-web.sh`: Download the repo from GitHub and launch the Ubuntu installer from a server bootstrap command
- `./scripts/deploy/ubuntu/bootstrap.sh`: Install blank-server Ubuntu prerequisites such as Docker and Tesseract
- `./scripts/deploy/ubuntu/configure.sh`: Run the first installer-style setup wizard and generate `.env.ubuntu`
- `./scripts/deploy/ubuntu/deploy.sh`: Build OCR helper image, ensure optional local Ollama, and start the Ubuntu deployment stack
- `./scripts/deploy/ubuntu/verify.sh`: Run post-install health checks against frontend, backend, Qdrant, Ollama, and OCR tooling
- `./scripts/deploy/ubuntu/start.sh`: Build and start the Ubuntu deployment stack
- `./scripts/deploy/ubuntu/stop.sh`: Stop the Ubuntu deployment stack
- `./scripts/deploy/ubuntu/status.sh`: Show deployment container status
- `./scripts/deploy/ubuntu/logs.sh backend`: Follow deployment logs
- `./scripts/deploy/ubuntu/update.sh`: Rebuild/restart the deployment stack and refresh pulled images
- `./scripts/deploy/ubuntu/cleanup.sh`: Stop deployment containers and prune unused Docker build/image leftovers
- `./scripts/clean-light.ps1`: Remove safe-to-regenerate caches and Docker build leftovers
- `./scripts/clean-deep.ps1`: More aggressive cleanup without deleting uploads or Qdrant data
- `./scripts/cleanup/reset-uploads.ps1 -Force`: Delete upload storage explicitly
- `./scripts/cleanup/reset-qdrant.ps1 -Force`: Delete Qdrant storage explicitly

## Data Layout

- `data/app/cache`: disposable app cache
- `data/qdrant`: persistent vector storage
- `data/uploads`: uploaded files
- `logs/backend`: backend logs and future runtime output
- `temp`: temporary disposable files

## Run (dev)

1. Start infrastructure services:

```powershell
./scripts/dev-up.ps1
```

2. Run preflight:

```powershell
./scripts/preflight.ps1
```

3. Start the backend:

```powershell
cd backend
py -3 -m uvicorn main:app --reload
```

4. Start the frontend in a second terminal:

```powershell
cd frontend
npm run dev
```

5. Open the app:

```text
http://localhost:3000
```

If Ollama is not running on `http://127.0.0.1:11434`, set `OLLAMA_BASE_URL` in `.env` before starting the backend.

## Troubleshooting

### Backend starts, but models do not load

If the app shows an Ollama error or `/models` returns `502 Bad Gateway`, check backend status first:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/status | Select-Object -ExpandProperty Content
```

Look at:

- `ollama.url`
- `ollama.status`
- `qdrant.status`

Common causes:

- Ollama is not running
- Backend is pointing to the wrong Ollama host
- Qdrant is not started

### Local Qdrant is not running

Start infrastructure services:

```powershell
./scripts/dev-up.ps1
```

Or repair just Qdrant:

```powershell
./scripts/dev/ensure-qdrant.ps1
```

`./scripts/dev-up.ps1` and `./scripts/dev/run-backend.ps1` now both verify that local Qdrant is healthy before continuing, and the backend also retries with a fresh Qdrant client after local restarts.

Then re-check:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/status | Select-Object -ExpandProperty Content
```

### External Ollama server is running, but the app still uses localhost

The backend must point to the Ollama API endpoint, not the remote web UI port.

Example:

- Wrong for Ollama API: `http://192.168.1.105:3000`
- Correct Ollama API example: `http://192.168.1.105:11434`

You can update the runtime setting from the app in `Settings`, or set it before backend startup with:

```powershell
$env:OLLAMA_BASE_URL="http://192.168.1.105:11434"
cd backend
py -3 -m uvicorn main:app --reload
```

### Quick checks

Check whether a remote host responds on the expected port:

```powershell
Test-NetConnection 192.168.1.105 -Port 11434
```

Check backend models directly:

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/models | Select-Object -ExpandProperty Content
```

### OCR for scanned or handwritten PDFs and images

Scanned PDFs, photos of documents, and handwritten/image-first files often do not contain embedded text, so normal extraction returns little or nothing. The backend now has an OCR fallback path for PDFs and common image formats, but it requires the Tesseract OCR engine to be installed locally.

Typical Windows path example:

```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

After installing Tesseract and updating `.env`, restart the backend and reprocess the document from `Knowledge`.

For scanned PDFs, Docker can now also be used as part of the OCR path through `OCRmyPDF`. If Docker is running, the backend can auto-build the helper image the first time that path is needed.

## Ubuntu Deploy

1. Copy `.env.ubuntu.example` to `.env.ubuntu` if the install script has not done it yet.
2. Review `OLLAMA_BASE_URL`, `NEXT_PUBLIC_API_BASE_URL`, and the exposed ports.
3. Run `./scripts/deploy/ubuntu/install.sh`.
4. Start the stack with `./scripts/deploy/ubuntu/start.sh`.
5. Check `./scripts/deploy/ubuntu/status.sh` and `./scripts/deploy/ubuntu/logs.sh`.

Installer-oriented Ubuntu phase flow now also exists:

1. `./scripts/deploy/ubuntu/installer.sh`

Or step-by-step:

1. `./scripts/deploy/ubuntu/bootstrap.sh`
2. `./scripts/deploy/ubuntu/configure.sh`
3. `./scripts/deploy/ubuntu/deploy.sh`
4. `./scripts/deploy/ubuntu/verify.sh`

The installer now also supports a first non-interactive path for automation:

```bash
./scripts/deploy/ubuntu/installer.sh \
  --non-interactive \
  --profile balanced \
  --ollama-mode external \
  --ollama-base-url http://10.0.0.20:11434 \
  --auth-mode required \
  --security-profile safe \
  --admin-username Admin \
  --admin-password-file /root/local-ai-os-admin-password \
  --public-url-scheme https \
  --data-root /opt/local-ai-os/data
```

The installer now supports two access modes:

- `required`: sign-in is enforced from the first page
- `open`: the app starts in local open mode and accounts can be enabled later

For most real deployments, `required` should stay the default.

The installer also supports a reusable answer file:

```bash
./scripts/deploy/ubuntu/installer.sh --non-interactive --answer-file ./scripts/deploy/ubuntu/answer-file.example.env
```

The example file lives here:

- `scripts/deploy/ubuntu/answer-file.example.env`

This is the easiest path when you want to reuse the same install profile across multiple servers.

There is also a recommended standard server profile:

- `scripts/deploy/ubuntu/answer-file.standard.env`

You can validate it before a real install with:

```bash
printf '%s\n' 'change-me-now' >/tmp/local-ai-os-admin-password
./scripts/deploy/ubuntu/configure.sh --non-interactive --validate-only --answer-file ./scripts/deploy/ubuntu/answer-file.standard.env
```

That standard profile keeps:

- sign-in required
- safe mode off
- OCR on
- local Ollama

Before deploy starts, the installer now prints a preflight summary of:

- profile
- Ollama mode and URL
- access mode
- bootstrap admin
- safe mode
- OCR
- connector features
- storage root
- ports and public API URL
- public URL scheme and secure-cookie mode

Interactive installs stop there for confirmation before deploy continues.

After a successful verify phase, the installer now writes an install report to:

- `${DATA_ROOT_HOST}/app/install/install-report-latest.md`

and also keeps a timestamped copy beside it.

The Ubuntu deployment uses:
- `infra/docker-compose.deploy.yml`
- `frontend/Dockerfile`
- persistent host storage under `data/`

For GitHub-hosted bootstrap installs on a fresh Ubuntu host, download and run:

```bash
curl -fsSL https://raw.githubusercontent.com/Palmen00/ai-platform/main/scripts/deploy/bootstrap-from-web.sh -o install-local-ai-os.sh
chmod +x install-local-ai-os.sh
./install-local-ai-os.sh
```

If the repo stays private, export a GitHub token first so the bootstrap script can clone it:

```bash
export GITHUB_TOKEN=your_token_here
./install-local-ai-os.sh
```

You can also forward installer automation flags through the bootstrap path:

```bash
export GITHUB_TOKEN=your_token_here
./install-local-ai-os.sh --installer-args "--non-interactive --profile balanced --auth-mode required --admin-username Admin --admin-password-file /root/local-ai-os-admin-password --public-url-scheme https"
```

## Retrieval Evals

Use the baseline eval suite to check whether the system is still finding the right documents as retrieval changes:

```powershell
./scripts/eval/retrieval.ps1
```

If Ollama is available and you also want to inspect model replies:

```powershell
./scripts/eval/retrieval.ps1 -WithReplies
```

To write a JSON report:

```powershell
./scripts/eval/retrieval.ps1 -WriteReport temp/retrieval-eval-report.json
```

The baseline suite is stored in `backend/evals/retrieval_baseline.json` and should grow as new document types and failure cases are discovered.

For harder OCR-backed and document-disambiguation checks:

```powershell
./scripts/eval/retrieval.ps1 -Suite backend/evals/retrieval_hard_cases.json
```

For reply-quality checks around more natural OCR/document answers:

```powershell
./scripts/eval/retrieval.ps1 -Suite backend/evals/reply_quality_cases.json -WithReplies
```

For broader coverage across the current uploaded document mix:

```powershell
./scripts/eval/retrieval.ps1 -Suite backend/evals/document_coverage_cases.json -WithReplies
```

## Structure
frontend/ -> UI
backend/ -> API
infra/ -> Docker & configs
data/ -> persistent data
scripts/ -> helpers
temp/ -> safe to delete
