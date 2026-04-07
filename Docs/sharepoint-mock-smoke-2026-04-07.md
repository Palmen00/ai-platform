# SharePoint Mock Smoke Test

## Summary

On April 7, 2026 we ran a live SharePoint mock smoke test against the deployed server at `192.168.1.105`.

The test used the SharePoint provider in `mock` mode, pointed at a mounted library path inside the backend container:

- `/app/data/sharepoint-smoke/library`

The library contained four representative files:

- `policy.docx`
- `metrics.xlsx`
- `roadmap.pptx`
- `scan-pdf.pdf`

## What We Verified

The smoke test exercised the full provider path, not just the document pipeline:

1. Admin login
2. SharePoint browse
3. Connector creation
4. Preview sync
5. Real sync
6. Document preview for each imported file
7. Chat grounding against each imported file

## Result

The final live run passed.

Representative result:

- login: pass
- browse: pass
- connector create: pass
- preview sync: pass
- real sync: pass
- docx preview/chat: pass
- xlsx preview/chat: pass
- pptx preview/chat: pass
- scanned pdf preview/chat: pass

The raw run artifacts are stored under:

- `temp/sharepoint-mock-smoke/`

Latest green run from this session:

- `temp/sharepoint-mock-smoke/sharepoint-mock-smoke-20260407-171608.md`
- `temp/sharepoint-mock-smoke/sharepoint-mock-smoke-20260407-171608.json`

## Product Bug Found And Fixed

The first live run exposed a real bug:

- SharePoint `mock` sync already worked
- but SharePoint `browse` was not wired into the provider dispatcher

That meant:

- `POST /connectors/browse` returned `501` for `provider=sharepoint`

The fix was added in:

- `backend/app/services/sharepoint_connector.py`
- `backend/app/services/connector_dispatcher.py`

## Notes

- The smoke test is intentionally idempotent now. On reruns it accepts already-synced documents being reported as `skipped` instead of forcing a fresh import every time.
- This test does not verify real Microsoft Graph auth. It verifies our own SharePoint-style provider logic, connector flow, and document/chat pipeline before a real tenant is available.
