# Local AI OS v0.1.0-rc1 Release Candidate Checklist

This checklist is the operator-facing gate for the first Linux server release candidate.

## Install Link

Fresh Ubuntu server install:

```bash
curl -fsSL -o install-local-ai-os.sh https://raw.githubusercontent.com/Palmen00/ai-platform/v0.1.0-rc1/scripts/deploy/bootstrap-from-web.sh
chmod +x install-local-ai-os.sh
./install-local-ai-os.sh --ref v0.1.0-rc1
```

Unattended install with an answer file:

```bash
./install-local-ai-os.sh \
  --ref v0.1.0-rc1 \
  --installer-args '--skip-bootstrap --non-interactive --answer-file /path/to/local-ai-os-answer.env'
```

## Answer File Template

```env
PROFILE=balanced
OLLAMA_MODE=external
OLLAMA_BASE_URL=http://host.docker.internal:11434
AUTH_MODE=required
SECURITY_PROFILE=standard
ADMIN_USERNAME=Admin
ADMIN_PASSWORD_FILE=/path/to/admin-password
DATA_ROOT=/home/ai/local-ai-os/data
FRONTEND_PORT=3000
BACKEND_PORT=8000
QDRANT_PORT=6333
HOSTNAME=192.168.1.105
PUBLIC_URL_SCHEME=http
OCR_ENABLED=yes
CONNECTOR_FEATURES_ENABLED=yes
```

## Fresh Install Checks

- Public GitHub raw link downloads `bootstrap-from-web.sh`.
- Installer clones `Palmen00/ai-platform` at `v0.1.0-rc1`.
- Configure writes `.env.ubuntu` with mode `600`.
- `.env.ubuntu` contains `ADMIN_PASSWORD_HASH_B64` and does not require `ADMIN_PASSWORD`.
- Docker stack starts `frontend`, `backend`, and `qdrant`.
- `verify.sh` passes backend, frontend, Qdrant, Ollama, Tesseract, and Docker-for-OCR checks.
- First login works with the configured bootstrap admin.
- Chat can create, save, list, and reload a conversation.
- Upload/OCR E2E passes for text, office, code, image, and scanned PDF fixtures.
- Unsupported executable upload is rejected.

## Update Checks

- Existing `DATA_ROOT` is reused.
- Existing conversations remain visible after the update.
- Existing uploaded documents remain visible after the update.
- Indexed document count remains stable or improves after startup processing settles.
- `verify.sh` passes after the update.
- Admin login still works after the update.

## Security Checks

- Protected admin endpoints reject unauthenticated requests.
- Viewer sessions cannot access admin endpoints.
- Admin sessions are stored in an `HttpOnly` cookie.
- `.env.ubuntu` is readable only by the owner.
- Connector secrets remain encrypted/redacted in public API responses.
- Runtime changes, logs, cleanup, backup import/export, connector actions, and user management require admin access.

## Current RC Evidence

The current server validation covered:

- Fresh install from public GitHub link.
- Upload/OCR E2E: 11/11 file-type cases passed.
- Enterprise document intelligence: 8/8 cases passed.
- Business document QA: 12/12 cases passed.
- Restart persistence: login, documents, indexing, conversations, Qdrant, and Ollama remained healthy.
