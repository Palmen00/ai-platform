# Linux Installer V1

This document defines the first real installer target for the product.

The goal is not a giant enterprise platform installer.
The goal is a stable, supportable bootstrap path for a new Linux server that starts from almost nothing and ends in a working Local AI OS deployment.

## Installer Goal

Take a new Ubuntu 24 server from:

- mostly empty host

to:

- working backend
- working frontend
- working vector database
- working OCR path
- working LLM runtime or external LLM connection
- sensible defaults
- minimal admin/security setup

with:

- one bootstrap link or command
- a short setup wizard
- post-install validation

## Product Principle

The installer should install what won for the product, not everything we ever tested.

That means:

- include the stable mainline stack
- exclude prototype-only tools
- keep the first release small enough to trust

## Installer Scope

### In Scope For V1

- blank Ubuntu 24 server bootstrap
- package installation
- Docker and Docker Compose setup
- app deployment setup
- runtime configuration wizard
- `Qdrant`
- `Tesseract`
- `OCRmyPDF` path
- `Ollama` local install or external Ollama configuration
- backend and frontend deployment
- persistent storage directory setup
- health checks
- service auto-start after reboot
- first admin account / password setup
- optional `safe mode`

### Out Of Scope For V1

- full enterprise SSO
- advanced role model beyond first admin foundation
- full multi-tenant isolation
- automatic Google/SharePoint OAuth onboarding in the installer
- prototype tools such as:
  - `Unstructured`
  - `Docling`
  - `Surya`
  - `EasyOCR`
  - `PaddleOCR`
  - `Marker`
  - `NanoChat`
  - `OpenViking`

## Winning Runtime Stack For Installer V1

The installer should treat this as the product baseline:

- app backend
- app frontend
- `Qdrant`
- `Tesseract`
- `OCRmyPDF`
- `Ollama` or external Ollama endpoint

### OCR Decision In Installer Terms

- primary scanned-PDF OCR: `OCRmyPDF`
- OCR fallback: `Tesseract`
- no experimental OCR engines in the default install

### Parsing Decision In Installer Terms

- native Office parsing stays enabled:
  - `docx`
  - `xlsx`
  - `pptx`
- text/code/config parsing stays enabled
- no prototype parsing stack in the default install

## Target Environment

### Primary Server OS

- Ubuntu 24 LTS

### Assumptions

- fresh or mostly fresh server
- sudo/root access available during installation
- outbound internet available during install
- enough disk to hold:
  - app images
  - vector storage
  - uploads
  - OCR artifacts
  - model data if local Ollama is chosen

## Installer Delivery Shape

V1 should be designed as a bootstrap installer, not a desktop wizard.

Recommended shape:

1. user runs a single install command from a published link
2. bootstrap script downloads the installer payload
3. installer asks a short set of questions
4. installer writes validated config
5. installer installs dependencies and starts services
6. installer runs post-install verification
7. installer prints:
   - app URL
   - admin login instructions
   - status commands
   - log commands

## Setup Wizard Questions

The wizard should be short and deliberate.

### 1. Deployment Profile

Options:

- `Light`
- `Balanced`
- `High Performance`

Purpose:

- choose CPU, memory, batching, and concurrency defaults

### 2. Ollama Mode

Options:

- `Install Ollama locally`
- `Use external Ollama server`

If external:

- ask for `OLLAMA_BASE_URL`

### 3. Security Profile

Options:

- `Standard`
- `Safe Mode`

Meaning:

- `Standard`: normal product defaults
- `Safe Mode`: stricter defaults, safer for sensitive company environments

### 4. Admin Setup

Ask for:

- admin password

Installer should then generate:

- `ADMIN_SESSION_SECRET`

### 5. Storage Location

Ask for:

- base data directory

Default example:

- `/opt/local-ai-os/data`

### 6. Network Setup

Ask for:

- frontend port
- backend bind port
- optional public hostname/domain

### 7. OCR Enablement

Options:

- `Enable OCR stack`
- `Disable OCR stack`

Recommended default:

- enabled

### 8. Connector Readiness

Options:

- `Enable connector features`
- `Disable connector features for now`

Meaning:

- this only enables product features
- it does not force OAuth setup during install

## Profile Defaults

### Light

Use when:

- smaller VM
- limited CPU/RAM
- shared host

Suggested defaults:

- lower concurrency
- smaller embedding batches
- conservative background processing
- `LOW_IMPACT_MODE=true`
- `GLiNER` off by default

### Balanced

Use when:

- normal single-server install
- recommended default

Suggested defaults:

- normal retrieval and indexing settings
- OCR enabled
- moderate concurrency
- `LOW_IMPACT_MODE=false`

### High Performance

Use when:

- stronger server
- larger document volumes
- more indexing throughput needed

Suggested defaults:

- larger batches
- higher concurrency
- more aggressive indexing defaults

## What The Installer Must Install

### System Packages

At minimum:

- `curl`
- `git`
- `ca-certificates`
- `docker`
- Docker Compose support
- `tesseract-ocr`
- required Tesseract language packs

If local Ollama selected:

- install `Ollama`

### App Components

- project code
- backend image
- frontend image
- deployment compose file
- OCR helper image build path

### Persistent Directories

The installer should create and validate:

- uploads
- app metadata
- extracted text
- chunks
- qdrant data
- logs
- backups

## Config The Installer Should Write

The installer should generate environment/config files from wizard answers.

That includes values such as:

- `OLLAMA_BASE_URL`
- `QDRANT_URL`
- `AUTH_ENABLED`
- `ADMIN_PASSWORD`
- `ADMIN_SESSION_SECRET`
- `SAFE_MODE`
- `LOW_IMPACT_MODE`
- ports and public API URL values
- storage path values where applicable

It should also choose profile-driven defaults for:

- retrieval settings
- chunking settings
- low-impact/high-performance toggles

## Service Model

V1 should favor a predictable Docker-based deployment.

Recommended runtime shape:

- frontend container
- backend container
- qdrant container
- OCR helper image available locally for backend-triggered OCRmyPDF jobs
- optional local Ollama service on host or external Ollama connection

The installer should also ensure:

- containers start automatically on reboot
- status can be checked with one documented command

## Post-Install Verification

The installer should verify:

- Docker is healthy
- app containers started
- backend health endpoint responds
- frontend responds
- Qdrant responds
- Ollama responds or external Ollama is reachable
- OCR dependencies are available if OCR was enabled

Recommended final output:

- app URL
- backend status URL
- admin login note
- commands for:
  - status
  - logs
  - restart
  - update

## Failure Handling

The installer should fail clearly, not continue with a half-broken stack.

Good failure points:

- Docker install failed
- Qdrant failed health check
- Ollama unreachable
- invalid external Ollama URL
- data directory not writable
- ports already occupied

The installer should report:

- what failed
- what was already installed
- what the operator should do next

## Security Expectations For V1

V1 is not the final enterprise security model.

But it should still enforce a better default than raw prototype mode.

Recommended baseline:

- admin auth enabled by default
- admin password required during install
- generated session secret
- optional `safe mode`
- no prototype tools installed by default
- no connector secrets requested during base install

## Support Philosophy

The installer should optimize for repeatability and support, not maximum flexibility.

That means:

- fewer choices
- better defaults
- clearer status output
- simpler recovery instructions

## Recommended Next Build Steps

1. turn this document into a concrete installer checklist
2. define exact wizard questions and env mappings
3. define profile-specific runtime defaults
4. adapt the Ubuntu deploy scripts into installer-safe phases:
   - bootstrap
   - configure
   - deploy
   - verify
5. only after that, build the actual install-link/bootstrap flow

The next concrete planning document is [Linux Installer V1 Checklist](./linux-installer-v1-checklist.md).
