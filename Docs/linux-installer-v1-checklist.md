# Linux Installer V1 Checklist

This document turns [Linux Installer V1](./linux-installer-v1.md) into a concrete build checklist.

The goal is to make the installer implementable without guessing.

## Build Goal

When this checklist is complete, we should be able to:

1. provision a mostly blank Ubuntu 24 server
2. run one bootstrap installer command
3. answer a short setup wizard
4. end with a healthy, supportable deployment

## Definition Of Done

Installer V1 is considered done when all of these are true:

- a blank Ubuntu 24 server can be bootstrapped with one command
- Docker and deploy dependencies are installed automatically
- the wizard writes a valid deploy env/config
- the product stack starts successfully
- post-install health checks pass
- the installer prints next-step commands for:
  - login
  - status
  - logs
  - restart
  - update
- the default install includes only the chosen product stack, not prototype tools

## Install Phases

The installer should be built in four explicit phases.

### Phase 1. Bootstrap

Responsible for:

- OS/package detection
- sudo/root validation
- internet/connectivity validation
- package manager prep
- Docker installation
- Docker Compose availability
- `git`
- `curl`
- `ca-certificates`
- `tesseract-ocr`
- required OCR language packs
- optional local `Ollama` installation

Outputs:

- host is ready to deploy containers
- installer runtime dependencies are available

### Phase 2. Configure

Responsible for:

- ask wizard questions
- validate answers
- generate secrets
- create data directories
- write deployment env file
- write installer state file if needed

Outputs:

- validated `.env.ubuntu` or installer-generated equivalent
- created storage directories
- clear runtime profile chosen

### Phase 3. Deploy

Responsible for:

- clone or update repo
- build backend image
- build frontend image
- pull/start `Qdrant`
- ensure OCR helper image path is available
- start deployment stack

Outputs:

- containers up
- restart policy active

### Phase 4. Verify

Responsible for:

- check backend health
- check frontend responds
- check `Qdrant`
- check `Ollama` or external Ollama reachability
- verify OCR prerequisites if OCR enabled
- print support commands and URLs

Outputs:

- successful install summary
- actionable failure summary if anything fails

## Wizard Questions And Env Mapping

The wizard should stay short.

### 1. Deployment Profile

Prompt:

- `Light`
- `Balanced`
- `High Performance`

Maps to:

- `LOW_IMPACT_MODE`
- `OLLAMA_EMBED_BATCH_SIZE`
- `RETRIEVAL_LIMIT`
- `DOCUMENT_CHUNK_SIZE`
- `DOCUMENT_CHUNK_OVERLAP`
- `GLINER_ENABLED`

### 2. Ollama Mode

Prompt:

- `Install Ollama locally`
- `Use external Ollama server`

Maps to:

- `OLLAMA_BASE_URL`
- optional host install of `Ollama`

If local:

- default `OLLAMA_BASE_URL=http://host.docker.internal:11434`

If external:

- ask for explicit API URL
- validate reachability before deploy

### 3. Security Profile

Prompt:

- `Standard`
- `Safe Mode`

Maps to:

- `AUTH_ENABLED=true`
- `SAFE_MODE=true|false`

Recommended v1 rule:

- admin auth should be enabled by default in both profiles
- `Safe Mode` only changes stricter behavior, not whether auth exists

### 4. Admin Setup

Prompt:

- admin password

Maps to:

- `ADMIN_PASSWORD`
- generated `ADMIN_SESSION_SECRET`
- optional `ADMIN_SESSION_TTL_HOURS`

Recommended default:

- `ADMIN_SESSION_TTL_HOURS=12`

### 5. Storage Location

Prompt:

- base data directory

Maps to:

- `DATA_ROOT`
- derived app directories inside that root

Recommended default:

- `/opt/local-ai-os/data`

### 6. Network Setup

Prompt:

- frontend port
- backend port
- qdrant port
- optional hostname/domain

Maps to:

- `FRONTEND_PORT`
- `BACKEND_PORT`
- `QDRANT_PORT`
- `NEXT_PUBLIC_API_BASE_URL`
- `BACKEND_CORS_ORIGINS`

### 7. OCR Enablement

Prompt:

- `Enable OCR`
- `Disable OCR`

Maps to:

- `OCR_ENABLED`
- `OCRMYPDF_ENABLED`

Recommended default:

- enabled

### 8. Connector Feature Readiness

Prompt:

- `Enable connector features`
- `Disable connector features for now`

Maps to:

- likely a product flag later
- not required to block base deployment

V1 note:

- this should not ask for Google or SharePoint secrets during base install

## Recommended Profile Defaults

These should be the installer defaults unless we later benchmark a better combination.

### Light

- `LOW_IMPACT_MODE=true`
- `GLINER_ENABLED=false`
- `OLLAMA_EMBED_BATCH_SIZE=2`
- `RETRIEVAL_LIMIT=3`
- `DOCUMENT_CHUNK_SIZE=900`
- `DOCUMENT_CHUNK_OVERLAP=120`
- `OCR_ENABLED=true`
- `OCRMYPDF_ENABLED=true`

Best for:

- small VM
- shared machine
- low-CPU environment

### Balanced

- `LOW_IMPACT_MODE=false`
- `GLINER_ENABLED=true`
- `OLLAMA_EMBED_BATCH_SIZE=8`
- `RETRIEVAL_LIMIT=4`
- `DOCUMENT_CHUNK_SIZE=1000`
- `DOCUMENT_CHUNK_OVERLAP=150`
- `OCR_ENABLED=true`
- `OCRMYPDF_ENABLED=true`

Best for:

- standard recommended install

### High Performance

- `LOW_IMPACT_MODE=false`
- `GLINER_ENABLED=true`
- `OLLAMA_EMBED_BATCH_SIZE=16`
- `RETRIEVAL_LIMIT=6`
- `DOCUMENT_CHUNK_SIZE=1200`
- `DOCUMENT_CHUNK_OVERLAP=180`
- `OCR_ENABLED=true`
- `OCRMYPDF_ENABLED=true`

Best for:

- stronger server
- higher ingest and retrieval volume

## Env File Minimum For Installer V1

The installer should produce at least these values:

```env
APP_ENV=prod
APP_NAME=Local AI OS

OLLAMA_BASE_URL=...
OLLAMA_DEFAULT_MODEL=llama3.2:3b
OLLAMA_EMBED_MODEL=nomic-embed-text

QDRANT_COLLECTION_NAME=document_chunks
RETRIEVAL_LIMIT=...
RETRIEVAL_MIN_SCORE=0.45
DOCUMENT_CHUNK_SIZE=...
DOCUMENT_CHUNK_OVERLAP=...

FRONTEND_PORT=3000
BACKEND_PORT=8000
QDRANT_PORT=6333
NEXT_PUBLIC_API_BASE_URL=...
BACKEND_CORS_ORIGINS=...

AUTH_ENABLED=true
ADMIN_PASSWORD=...
ADMIN_SESSION_SECRET=...
ADMIN_SESSION_TTL_HOURS=12
SAFE_MODE=...

LOW_IMPACT_MODE=...
OCR_ENABLED=...
OCRMYPDF_ENABLED=...
GLINER_ENABLED=...
OLLAMA_EMBED_BATCH_SIZE=...

DATA_ROOT=...
```

## Directory Checklist

Installer should create and verify:

- data root
- uploads
- app metadata
- conversations
- document chunks
- extracted text
- connectors
- app logs
- qdrant storage
- temp/cache if needed

Recommended root:

- `/opt/local-ai-os`

Recommended storage:

- `/opt/local-ai-os/data`

## Runtime Components Checklist

Must be present in V1:

- frontend container
- backend container
- qdrant container
- OCR helper image path for `OCRmyPDF`
- local or external `Ollama`

Must not be installed by default:

- `Unstructured`
- `Docling`
- `Surya`
- `EasyOCR`
- `PaddleOCR`
- `Marker`

## Post-Install Verification Checklist

Installer must verify:

- Docker daemon healthy
- compose config valid
- backend container running
- frontend container running
- qdrant container running
- backend health endpoint returns success
- backend status endpoint returns success
- frontend root responds
- qdrant collections endpoint responds
- Ollama reachable
- OCR path configured if enabled

Good checks:

- `GET /health`
- `GET /status`
- `GET /models`
- `GET http://127.0.0.1:${QDRANT_PORT}/collections`

## Failure Messages We Need

The installer should have explicit failure categories for:

- unsupported OS or version
- no sudo/root access
- Docker install failure
- compose validation failure
- invalid external Ollama URL
- Ollama unreachable
- storage path not writable
- required port already in use
- backend failed health check
- frontend failed health check
- qdrant failed health check

## Support Output Checklist

At the end of a successful install, print:

- frontend URL
- backend health URL
- backend status URL
- admin sign-in note
- storage root
- whether OCR is enabled
- whether safe mode is enabled
- whether Ollama is local or external

And print these commands:

- start
- stop
- restart
- status
- logs
- update

## Build Tasks

### Checklist A. Installer Script Design

- define bootstrap entrypoint
- add a top-level installer wrapper that can run all phases in order
- define non-interactive mode shape for later automation
- define env file generation strategy
- define secret generation strategy

Status:

- a first GitHub bootstrap entrypoint now exists at `scripts/deploy/bootstrap-from-web.sh`
- it can fetch from a public GitHub repo directly
- it can also clone a private GitHub repo when a token such as `GITHUB_TOKEN` is provided
- next improvement is to add a more guided non-interactive/server-automation mode on top

### Checklist B. Ubuntu Script Refactor

- split current Ubuntu deploy logic into reusable phases:
  - bootstrap
  - configure
  - deploy
  - verify
- keep current scripts usable during the transition

### Checklist C. Config/Template Work

- extend `.env.ubuntu.example` to cover installer needs
- add profile templates or profile-mapping logic
- define generated values vs user-provided values

### Checklist D. Verification Layer

- create installer-safe health checks
- create friendly success/failure output
- make post-install diagnostics reproducible

## Recommended Immediate Next Step

The next implementation step should be:

1. refactor the Ubuntu deployment scripts into the four installer phases
2. add a generated-config step for wizard answers
3. then build the bootstrap entrypoint around those pieces

That keeps the installer grounded in the deploy path we already have, instead of creating a second deployment system from scratch.
