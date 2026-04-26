# Local AI OS v0.1.0-rc1 Release Notes

Date: 2026-04-26

`v0.1.0-rc1` is the first installer-ready release candidate for the local server build.

## Install

```bash
curl -fsSL -o install-local-ai-os.sh https://raw.githubusercontent.com/Palmen00/ai-platform/v0.1.0-rc1/scripts/deploy/bootstrap-from-web.sh
chmod +x install-local-ai-os.sh
./install-local-ai-os.sh --ref v0.1.0-rc1
```

## Included

- Ubuntu installer bootstrap from a public GitHub tag.
- Docker-based backend, frontend, Qdrant, Ollama, and OCR helper stack.
- Local account auth with admin and viewer roles.
- Saved conversations scoped to the signed-in account.
- Document upload, extraction, OCR fallback, chunking, indexing, preview, and chat retrieval.
- Document intelligence metadata for family grouping, version hints, topics, and cached similarity links.
- Idle maintenance backfill for older documents when the server is quiet.
- Settings sections for overview, runtime, retrieval, documents, storage, cleanup, security, users, audit, backups, logs, and models.
- Minimal UI style guide for compact admin-console screens.
- Security hardening around session cookies, env file permissions, admin-only routes, and safe-mode guarded actions.

## Verified

- Fresh/update install from `v0.1.0-rc1` on the Ubuntu server path.
- Post-install backend, frontend, Qdrant, Ollama, and OCR checks.
- Login with admin account.
- Existing conversations and documents preserved across update.
- Viewer role denied access to logs and user management.
- Admin role allowed access to logs and user management.
- Business document QA suite passed 12/12 cases against the server.
- Frontend lint and production build passed locally.
- Backend compile check passed locally.

## Known Notes

- The current release candidate should be treated as a beta candidate, not a final production release.
- The installer is ready for controlled server testing, but a full destructive reinstall should wait until the target server is available.
- The Next.js build may warn about multiple lockfiles if there is an unrelated `package-lock.json` above the project directory.
- Google Drive and SharePoint-style live connector tests are intentionally not part of this RC validation unless credentials are configured.

## Next Priorities

1. Run a real fresh reinstall on the Ubuntu server from the public tag.
2. Keep polishing the compact settings/admin UI style across remaining screens.
3. Expand natural document QA scenarios and regression tests.
4. Add clearer first-run install prompts for auth mode, admin account, model choice, and safe mode.
5. Prepare a second release candidate only after the reinstall path is proven clean.
