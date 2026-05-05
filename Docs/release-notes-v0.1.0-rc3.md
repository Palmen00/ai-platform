# Local AI OS v0.1.0-rc3 Release Notes

Date: 2026-05-05

`v0.1.0-rc3` is a hotfix release candidate after the broad server check on the Ubuntu install. It keeps the rc2 installer path but fixes a document deletion race found during upload/OCR stress testing.

## Install

```bash
curl -fsSL -o install-local-ai-os.sh https://raw.githubusercontent.com/Palmen00/ai-platform/v0.1.0-rc3/scripts/deploy/bootstrap-from-web.sh
chmod +x install-local-ai-os.sh
./install-local-ai-os.sh --ref v0.1.0-rc3
```

## Hotfix

- Deleting a document now creates a deletion marker before files and metadata are removed.
- Background document processing checks that marker before writing metadata back.
- This prevents a deleted document from reappearing if it was removed while OCR/extraction/indexing was still running.
- The server was patched and rebuilt with this fix.

## Verified

- Ubuntu `verify.sh`: passed.
- Backend compile check: passed.
- Frontend lint: passed.
- Frontend production build: passed.
- Commercial extraction unit smoke: passed.
- Upload/OCR E2E: 11/11 passed, unsupported `.exe` rejected.
- Invoice/product QA: 8/8 passed.
- Enterprise document intelligence: 8/8 passed.
- Broad API/security/performance smoke: passed.
- Delete-race smoke after the hotfix: passed.

## Known Notes

- The broad check exposed documents uploaded outside the test fixtures. Those were not part of the generated test data, so future cleanup must only delete IDs explicitly created by the active test run.
- Existing rc2 tags are not rewritten. Use rc3 or newer for fresh installs.
