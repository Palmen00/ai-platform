# Session Handoff 2026-05-07

This checkpoint closes the May 7 invoice/RAG reliability, source UX, server
profile, and hardening pass.

## Current Product State

The live server is healthy after the final backend and frontend deploy.

- server: `192.168.1.105`
- branch: `main`
- backend: `ok`
- frontend: `ok`
- Ollama: `ok`
- Qdrant: `ok`
- documents total: `191`
- Qdrant indexed points: `2127`
- failed documents: `0`

## What Changed

- Improved invoice and product retrieval so exact line-item questions such as
  "Which invoice mentions Carbon Brake Pads?" are matched against extracted
  commercial line items before generic source summarization can answer from the
  wrong source.
- Fixed invoice batch handling so `batch-YYYYMMDD` style markers are not
  treated as invoice IDs or monetary values.
- Added multi-invoice aggregate answers for supplier totals and total spend
  across a selected invoice batch.
- Expanded invoice QA to three realistic invoices and added checks for product
  lookup, product inventory, highest invoice, supplier breakdown, and total
  spend.
- Added a runtime profile script for API latency plus optional SSH snapshots of
  uptime, memory, disk, Docker status, and Docker resource use.
- Added a production hardening script for auth, cookie flags, dependency
  health, failed documents, audit logs, tracked secret filenames, and tracked
  private-key blocks.
- Added frontend source actions for scoped source summaries and invoice facts.
- Added chat draft tools for invoice analysis, source comparison, and support
  replies.

## Verification

Local checks:

- `py -3 -m py_compile backend/app/services/documents.py backend/app/services/retrieval.py`
- `py -3 -m py_compile scripts/tests/run_invoice_document_qa_suite.py scripts/tests/run_server_runtime_profile.py scripts/tests/run_production_hardening_check.py`
- `npm run lint`
- frontend production build passed during Docker rebuild

Live server checks:

- invoice document QA: `14/14`
- production hardening: `10/10`, critical failures `0`
- runtime profile: status `ok`
- frontend `/`: HTTP `200`
- backend `/health`: `ok`

Reports:

- `temp/invoice-document-qa/invoice-document-qa-20260507-102738.md`
- `temp/production-hardening/production-hardening-20260507-102743.md`
- `temp/server-runtime-profile/server-runtime-profile-20260507-102914.md`

## Notes

- The SSH key for server automation is `C:\Users\oskar\.ssh\local-ai-os-server`.
- Server-side deploy was done by copying changed files into
  `/home/ai/.local-ai-os-standard-link-install` and rebuilding Docker services.
- The live server now has the May 7 backend and frontend changes, but the local
  Git changes still need to be committed and pushed if that has not happened in
  the next step.

## Recommended Next Step

1. Commit and push the May 7 reliability and test-suite changes.
2. Add a source-detail dropdown/panel in the chat UI so users can inspect
   multiple invoice/document sources without reading a wall of text.
3. Add source-specific follow-up state so a user can click one invoice and ask
   follow-up questions constrained to that source.
4. Keep expanding real-world invoice, receipt, quote, incident, and report
   writing tests.
5. Plan a fresh GitHub link-install reinstall when the server can be wiped
   safely.
