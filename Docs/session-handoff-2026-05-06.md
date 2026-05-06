# Session Handoff 2026-05-06

This checkpoint closes the May 6 live-server document QA and Writing workspace
hardening pass.

## Current Product State

The live server is healthy and aligned to the pushed May 6 commit.

- server: `192.168.1.105`
- commit: `4f33191`
- branch: `main`
- backend: `ok`
- Ollama: `ok`
- Qdrant: `ok`
- documents total: `165`
- processed/indexed: `165 / 165`
- failed documents: `0`
- `Google cert.pdf`: retried and no longer stuck
- document-intelligence stale/background backlog: `0`

## What Changed

- Fixed named-batch filtering so invoice/product inventory questions scoped to a
  batch marker do not include unrelated invoices.
- Improved company/entity cleanup so invoice/company answers do not return UI
  fragments such as "Learn more" as companies.
- Added direct structured fallbacks for config/XML port lookups and explicit
  invoice identifiers such as `INV-77`.
- Strengthened Writing workspace prompting so report/email/action-plan requests
  keep the requested structure and mark missing fields as `Unknown`.
- Added a source-grounded action-plan fallback that creates a table with task,
  owner, deadline, priority, and evidence instead of producing a weak refusal.
- Added a source-grounded customer-email fallback that still creates a usable
  email draft when retrieved incident details are incomplete.
- Hardened Ubuntu `update.sh` so GitHub-based installs can fast-forward from
  upstream, `origin/<branch>`, or `FETCH_HEAD`, and marked deploy scripts
  executable in Git.
- Fixed weak OCR titles such as `Nr` by falling back to filename-derived
  document family keys and labels.
- Added `scripts/tests/run_writing_workspace_suite.py` so the Writing workspace
  can be retested consistently against the live server.

## Verification

Local checks:

- `py -3 -m compileall backend/app`
- `py -3 scripts/tests/test_chat_metadata_regressions.py`
- `py -3 scripts/tests/test_commercial_extraction.py`

Live server checks:

- system stability: passed
- invoice document QA: `8/8`
- document follow-up regression: `11/11`
- business document QA: `12/12`
- Writing workspace: `4/4`
- GitHub fresh install on isolated ports `3100/8100/6433`: passed
- GitHub update flow after fresh install: passed
- final `/status`: backend, Ollama, and Qdrant all `ok`

Reports:

- `temp/system-stability/system-stability-20260506-081523.md`
- `temp/system-stability/system-stability-20260506-100202.md`
- `temp/invoice-document-qa/invoice-document-qa-20260506-083930.md`
- `temp/document-followup-regression/followup-regression-20260506-085423.md`
- `temp/business-document-qa/business-document-qa-20260506-090411.md`
- `temp/writing-workspace/writing-workspace-20260506-101524.md`

## Important Caveat

The current fixes are pushed and the live server is aligned to `main`.

A safety stash named `codex-manual-deploy-2026-05-06` remains on the server from
the earlier manual deploy. It should not be applied unless we intentionally need
to inspect that temporary state.

## Recommended Next Step

1. Keep GitHub install/update smoke in the release-candidate gate.
2. Run the next destructive reinstall only when the server can be safely wiped.
3. Add a visible operator button for stale document-intelligence refreshes.
4. Continue expanding live document QA with real customer, invoice, incident,
   and report-writing scenarios.
