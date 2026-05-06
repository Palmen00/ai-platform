# Developer Runbook: Local AI OS Support

## Purpose

This runbook describes operational support tasks for Local AI OS validation
environments. It is intentionally written as realistic knowledge-base content
for AI capability testing.

## Health checks

Use these checks before debugging application behavior:

- Frontend: `GET /` should return a web page.
- Backend health: `GET /health` should return `{"status": "ok"}`.
- Backend status: `GET /status` should include Ollama, Qdrant, storage, and
  document-intelligence status.
- Qdrant: `GET /collections/document_chunks` should return collection metadata.

## Deployment commands

The Ubuntu deployment helper scripts live in `scripts/deploy/ubuntu`.

- Start stack: `./scripts/deploy/ubuntu/start.sh`
- Stop stack: `./scripts/deploy/ubuntu/stop.sh`
- Update stack: `./scripts/deploy/ubuntu/update.sh`
- Verify stack: `./scripts/deploy/ubuntu/verify.sh`
- Backend logs: `./scripts/deploy/ubuntu/logs.sh backend`

## Backup worker

The backup worker writes a compressed runtime snapshot into the configured
backup directory. The expected backup job name is `local-ai-os-nightly-backup`.
The worker must not include raw `.env` files, OAuth client secrets, private
keys, or session cookies in the export.

## Escalation checklist

Escalate to engineering when:

- `/status` reports Qdrant unreachable for more than 5 minutes.
- Document indexing remains pending for more than 20 minutes.
- The frontend can sign in but saved chats cannot be loaded.
- The model generates answers without sources for a document-scoped question.

## Known-safe answer style

When the material is incomplete, the assistant should say what is missing and
ask for the exact document, log excerpt, timestamp, or environment details it
needs. It should not invent service names, credentials, or private network
details.
