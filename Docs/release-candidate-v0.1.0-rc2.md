# Local AI OS v0.1.0-rc2 Release Candidate Checklist

This checklist is the operator-facing gate for the second Linux server release candidate.

## Install Link

Fresh Ubuntu server install:

```bash
curl -fsSL -o install-local-ai-os.sh https://raw.githubusercontent.com/Palmen00/ai-platform/v0.1.0-rc2/scripts/deploy/bootstrap-from-web.sh
chmod +x install-local-ai-os.sh
./install-local-ai-os.sh --ref v0.1.0-rc2
```

Unattended install with an answer file:

```bash
./install-local-ai-os.sh \
  --ref v0.1.0-rc2 \
  --installer-args '--skip-bootstrap --non-interactive --answer-file /path/to/local-ai-os-answer.env'
```

## Standard Answer File Shape

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

Security rule:

- `ADMIN_PASSWORD_FILE` is preferred.
- Do not commit a real password in an answer file.
- `Admin` / `password` is only for local test installs.

## Fresh Install Checks

- Public GitHub raw link downloads `bootstrap-from-web.sh`.
- Installer clones `Palmen00/ai-platform` at `v0.1.0-rc2`.
- Configure writes `.env.ubuntu` with mode `600`.
- `.env.ubuntu` contains `ADMIN_PASSWORD_HASH_B64` and does not contain `ADMIN_PASSWORD=`.
- Docker Compose project name is unique to the install path.
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
- Public frontend API URL remains pointed at the selected backend host and port.

## Security Checks

- Protected admin endpoints reject unauthenticated requests.
- Viewer sessions cannot access admin endpoints.
- Admin sessions are stored in an `HttpOnly` cookie.
- `.env.ubuntu` is readable only by the owner.
- Connector secrets remain encrypted or redacted in public API responses.
- Runtime changes, logs, cleanup, backup import/export, connector actions, and user management require admin access.
- Standard profile defaults to `SAFE_MODE=false`.
- Safe profile can be selected when operators want stricter runtime blocking.

## Backup And Restore Checks

- App backup export returns runtime settings, document metadata, and conversations.
- App backup import restores runtime settings and conversations and reports skipped document metadata.
- Filesystem backup captures app data and Qdrant storage.
- Filesystem backup can be restored into an isolated backend+Qdrant smoke stack.
- Restored stack allows admin login and lists expected documents.
- Restore smoke stack is stopped and removed after validation.

## Current rc2 Evidence

The current server validation covered:

- Public-link standard install remained healthy on Ubuntu.
- Invoice document QA: 8/8 cases passed.
- System stability smoke passed.
- App backup export/import passed with 4 documents and 0 conversations.
- Filesystem backup/restore smoke passed in an isolated stack on ports `8200` and `6533`.
- Security smoke passed for unauthenticated rejection, wrong-password rejection, admin login, protected admin routes, env file mode, and missing cleartext secrets.

## Release Gate

Before this tag is considered ready for broader beta use:

- Push the `v0.1.0-rc2` tag.
- Run one full fresh reinstall from that exact tag when the server can be wiped.
- Confirm chat persistence, upload/OCR, document retrieval, invoice/product questions, backup export/import, and security smoke again after the destructive reinstall.
