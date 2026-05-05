# Session Handoff 2026-05-05

This is the checkpoint after the first serious live-server chat and retrieval
validation pass.

## Current Product State

The project is now in MVP hardening against a real deployed server, not only
local development.

Live server status at the checkpoint:

- server: `192.168.1.105`
- backend: `ok`
- Ollama: `ok`
- Qdrant: `ok`
- documents total: `143`
- processed/indexed: `142 / 142`
- failed documents: `0`
- known pending document: `Google cert.pdf`

## What Changed

- Deployed the current local retrieval and document fixes to the live server.
- Rebuilt backend/frontend Docker images on the server.
- Kept existing uploaded documents, Qdrant storage, and account data intact.
- Improved direct metadata-backed chat answers so they keep sources.
- Improved natural-language routing for:
  - latest uploaded document
  - Swedish invoice/company prompts
  - invoice totals and amounts
  - ordered products and services
  - bike-related purchase questions
  - follow-up questions about the previously referenced document
- Added duplicate-upload warning support in the upload response and Knowledge UI.
- Added optional `Remember me` login with a configurable long-session TTL.
- Added first-pass chat draft helpers for:
  - customer emails
  - incident reports
  - management summaries
  - action plans
- Added the first Writing workspace selector in the chat composer.
- Added source workflow actions so a source can be previewed, used as the next
  question scope, or used as the starting point for comparison.
- Improved invoice intelligence for:
  - most/least expensive invoice questions
  - invoice issued/date follow-ups
  - bullet-list invoice and product summaries
  - line-item total fallback when top-level invoice totals are incomplete
- Tightened routing so general coding questions do not accidentally enter
  uploaded-document mode.

## Verification

Local checks:

- `py -3 -m compileall backend/app`
- `py -3 scripts/tests/test_chat_metadata_regressions.py`

Server checks:

- backend health passed after rebuild
- `/status` reported backend, Ollama, and Qdrant as healthy
- broad live conversation suite: `26/30`
- focused live regression after the final retrieval patch: `8/8`
- live auth/source/invoice/upload regression: `12/12`
- remember-me server check:
  - normal login cookie: `Max-Age=43200`
  - remember-me cookie: `Max-Age=2592000`

Reports:

- `temp/live-conversation-check/live-conversation-check-20260505-143757.md`
- `temp/live-conversation-check/live-focused-regression-20260505-150158.md`
- `temp/live-regression/live-regression-20260505-214212.md`

## Important Caveat

The latest fixes are present locally and deployed manually to the server, but
they are not committed or pushed yet.

That means a fresh GitHub install or update will not receive these fixes until
the current working tree is committed and pushed.

## Known Issues

- `Google cert.pdf` is still pending/indexing.
- The broad live suite still showed some weak broad-answer behavior before the
  final focused patch, so the next broad suite should be rerun after commit.
- Some broad invoice summaries are useful but still noisy and need better
  ranking and cleaner grouping.
- Prompt-injection handling passed the focused gate, but should keep expanding
  with more adversarial cases.

## Recommended Next Step

1. Commit and push the current local changes.
2. Run a GitHub-based update/install path to prove the server can reproduce the
   current deployed code without manual patch copying.
3. Retry or resolve `Google cert.pdf`.
4. Rerun the broad live conversation suite after the push/update path is proven.
5. Test the Writing workspace against more real incident/customer-response documents.
