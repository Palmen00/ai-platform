# Local AI OS v0.1.0-rc4 Release Notes

Date: 2026-05-06

`v0.1.0-rc4` is the next release-candidate target after validating the public
GitHub install and update path on the live Ubuntu server.

## Highlights

- Public GitHub bootstrap install passed in an isolated server install.
- GitHub update flow now pulls code safely before rebuilding.
- Deploy/support scripts are executable when cloned from GitHub.
- Live document-intelligence backlog is cleared: `0` stale, `0` pending.
- Weak OCR titles such as `Nr` now fall back to filename-derived document
  families instead of staying stale forever.
- Writing workspace now has grounded fallbacks for customer emails and action
  plans, reducing weak refusal-style answers when documents are incomplete.

## Verified

- Fresh GitHub install smoke: passed.
- Fresh GitHub update smoke: passed.
- Ubuntu `verify.sh`: passed on isolated and live installs.
- System stability: passed.
- Writing workspace: `4/4`.
- Invoice QA: `8/8`.
- Document follow-up regression: `11/11`.
- Business document QA: `12/12`.
- Live `/status`: backend, Ollama, Qdrant all `ok`; `165/165` documents
  processed/indexed; `0` failed.

## Known Notes

- The isolated fresh-install stack was stopped after validation.
- A destructive reinstall from a wiped server is still the final confidence gate
  before tagging this release candidate.
- Existing installs older than the updated `update.sh` may need one manual
  `git fetch origin main && git merge --ff-only FETCH_HEAD` before future
  `./scripts/deploy/ubuntu/update.sh` runs can self-update normally.
