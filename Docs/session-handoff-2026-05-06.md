# Session Handoff 2026-05-06

This checkpoint closes the May 6 live-server document QA and Writing workspace
hardening pass.

## Current Product State

The live server is healthy and running the manually deployed May 6 backend fixes.

- server: `192.168.1.105`
- backend: `ok`
- Ollama: `ok`
- Qdrant: `ok`
- documents total: `154`
- processed/indexed: `154 / 154`
- failed documents: `0`
- `Google cert.pdf`: retried and no longer stuck
- maintenance note: document intelligence still reports `1` stale/background item
  after a manual refresh, but no document is failed or unindexed

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
- final `/status`: backend, Ollama, and Qdrant all `ok`

Reports:

- `temp/system-stability/system-stability-20260506-081523.md`
- `temp/invoice-document-qa/invoice-document-qa-20260506-083930.md`
- `temp/document-followup-regression/followup-regression-20260506-085423.md`
- `temp/business-document-qa/business-document-qa-20260506-090411.md`
- `temp/writing-workspace/writing-workspace-20260506-092806.md`

## Important Caveat

The current server contains manually copied backend files because the GitHub
push is blocked by local GitHub credentials.

Until credentials are refreshed and the commits are pushed, a fresh public
GitHub install/update will not reproduce the exact live server state.

## Recommended Next Step

1. Commit the May 6 remaining changes locally.
2. Refresh GitHub credentials and push.
3. Re-align the live server with GitHub using the normal update/install path.
4. Add an operator-friendly flow for stale document-intelligence refreshes.
5. Continue expanding live document QA with real customer, invoice, incident,
   and report-writing scenarios.
