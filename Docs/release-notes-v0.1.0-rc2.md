# Local AI OS v0.1.0-rc2 Release Notes

Date: 2026-05-04

`v0.1.0-rc2` is the second installer-ready release candidate for the local server build. It focuses on the public GitHub install path, account-backed chat persistence, invoice/product intelligence, backup confidence, and a tighter security smoke baseline.

## Install

```bash
curl -fsSL -o install-local-ai-os.sh https://raw.githubusercontent.com/Palmen00/ai-platform/v0.1.0-rc2/scripts/deploy/bootstrap-from-web.sh
chmod +x install-local-ai-os.sh
./install-local-ai-os.sh --ref v0.1.0-rc2
```

For unattended installs, prefer a password file instead of inline secrets:

```env
ADMIN_USERNAME=Admin
ADMIN_PASSWORD_FILE=/path/to/admin-password
```

`Admin` / `password` is acceptable only for local test environments. Change it during real installs.

## Added Since rc1

- Public web bootstrap can target the current release tag cleanly.
- Deploy stacks derive unique Docker Compose project names so test installs do not collide.
- Frontend/backend public URL handling is preserved through the installer flow.
- Connector stability checks are optional so missing Google/SharePoint credentials do not block the base install.
- Commercial document parsing now extracts invoice numbers, dates, totals, VAT/tax, due dates, and product line items more reliably.
- Document list and preview views expose cached commercial summaries so invoice/product questions have structured context.
- A dedicated invoice document QA suite now validates product, cost, and supplier-style questions.

## Verified On Server

- Standard public-link install remained healthy on Ubuntu with frontend `3000`, backend `8000`, and Qdrant `6333`.
- Login with `Admin` / `password` works in the test environment.
- Chat persistence and document visibility survived the update path.
- Invoice document QA passed 8/8 cases against the current server.
- System stability smoke passed for backend health, auth, documents, indexing, Qdrant, and Ollama reachability.
- App backup export/import succeeded with 4 documents and 0 conversations in the current clean test state.
- Filesystem backup restored into an isolated backend+Qdrant smoke stack on ports `8200` and `6533`; login worked and 4 documents were visible.
- Security smoke passed:
  - unauthenticated `/documents` returned `401`
  - wrong admin password returned `401`
  - admin login returned `200`
  - authenticated `/documents`, `/auth/users`, and `/auth/status` returned `200`
  - `.env.ubuntu` mode is `600`
  - `.env.ubuntu` has no `ADMIN_PASSWORD=` cleartext entry
  - Google/SharePoint connector secrets are not set in the server env

## Known Notes

- `SAFE_MODE=false` is the standard install baseline. Use `SECURITY_PROFILE=safe` when an operator wants stricter runtime blocking around cleanup, backup import/export, and risky admin actions.
- `ADMIN_SESSION_COOKIE_SECURE=false` is expected for the current HTTP-only LAN test install. Use HTTPS in production so secure cookies can be enabled.
- App-level backup import restores runtime settings and conversations. Full document/vector recovery currently uses the filesystem backup path.
- Google Drive and SharePoint live connector tests still require real credentials and were intentionally skipped.
- The current server validation used a clean test state with 4 starter documents and 0 saved conversations.

## Next Priorities

1. Run one destructive fresh reinstall from the `v0.1.0-rc2` tag when the server can be fully wiped again.
2. Promote filesystem backup/restore into a documented operator command instead of only a smoke-test procedure.
3. Keep expanding invoice, product, and commercial document QA against real uploaded invoices.
4. Add first-run guidance that makes `Admin` / `password` impossible to keep accidentally in production.
5. Add live connector validation once Google Drive or SharePoint credentials are available.
