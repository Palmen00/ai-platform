# Local AI OS v0.1.0-rc4 Release Candidate Checklist

Date: 2026-05-06

This checklist captures the current GitHub install/update gate after the live
server hardening pass.

## Candidate Commit

- Current commit: `4f33191`
- Branch: `main`
- Live server: `192.168.1.105`
- Live server state: healthy and aligned to `main`

## Install Link Smoke

Validated with an isolated install on the existing Ubuntu server using:

- install root: isolated timestamped home-directory checkout
- data root: isolated timestamped home-directory data path
- frontend port: `3100`
- backend port: `8100`
- Qdrant port: `6433`
- Ollama mode: external, pointed at the existing local Ollama service
- auth mode: required
- security profile: standard
- OCR: enabled
- connectors: enabled

Result:

- public GitHub raw bootstrap downloaded successfully
- repository cloned from `Palmen00/ai-platform`
- bootstrap/configure/deploy/verify completed successfully
- `.env.ubuntu` was written with mode `600`
- no `ADMIN_PASSWORD=` cleartext value was written to `.env.ubuntu`
- admin login worked with the generated password file
- remember-me auth cookie was issued
- document upload worked
- duplicate-upload warning worked
- uploaded smoke documents processed and indexed
- chat answered from the uploaded smoke document with a source
- temporary raw password and answer files were removed after validation
- isolated test stack was stopped after validation

## Update Smoke

Validated update behavior on both the isolated install and the live install.

Result:

- deploy scripts are executable in Git
- `update.sh` refuses to run over a dirty checkout
- `update.sh` can fast-forward when an upstream is configured
- `update.sh` can fast-forward through `origin/<branch>` or `FETCH_HEAD` when
  older installer checkouts have narrow or missing refspecs
- post-update `verify.sh` passed

## Live Server Status

Current live `/status` after update:

- backend: `ok`
- Ollama: `ok`
- Qdrant: `ok`
- documents: `165`
- processed/indexed: `165 / 165`
- failed documents: `0`
- document-intelligence stale backlog: `0`
- maintenance pending documents: `0`

## Writing And Retrieval Gate

Current validated behavior:

- invoice QA: `8/8`
- document follow-up regression: `11/11`
- business document QA: `12/12`
- system stability: passed
- Writing workspace: `4/4`
- customer email drafting has a grounded fallback
- action-plan drafting has a grounded table fallback
- weak OCR titles fall back to filename-derived family keys

Latest reports:

- `temp/system-stability/system-stability-20260506-100202.md`
- `temp/writing-workspace/writing-workspace-20260506-101524.md`

## Release Gate Before Tagging

Before tagging `v0.1.0-rc4`:

- run one destructive reinstall only when the server can be safely wiped
- rerun upload/OCR E2E after destructive reinstall
- rerun invoice QA, business QA, Writing workspace, and system stability
- confirm backup/export remains healthy after reinstall
- confirm the fresh install starts cleanly after host reboot

## Known Notes

- The isolated fresh-install stack was stopped after validation to avoid
  consuming ports and resources.
- The isolated test data root was kept for auditability and can be deleted later
  if disk cleanup is needed.
- A safety stash named `codex-manual-deploy-2026-05-06` remains on the live
  server from an earlier manual patching step. It should not be applied unless
  intentionally inspected.
