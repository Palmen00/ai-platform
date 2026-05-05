# Documentation

This folder now uses Markdown as the primary documentation format.

## Recommended Reading Order

1. [Vision](./vision.md)
2. [MVP](./mvp.md)
3. [Architecture](./architecture.md)
4. [OCR Decision](./ocr-decision.md)
5. [Security Risk Register](./security-risk-register.md)
6. [Connector Routing](./connector-routing.md)
7. [Tech Stack](./tech-stack.md)
8. [Current Features](./current-features.md)
9. [Installation Plan](./installation-plan.md)
10. [Linux Installer V1](./linux-installer-v1.md)
11. [Linux Installer V1 Checklist](./linux-installer-v1-checklist.md)
12. [v0.1.0-rc3 Release Notes](./release-notes-v0.1.0-rc3.md)
13. [v0.1.0-rc2 Release Candidate Checklist](./release-candidate-v0.1.0-rc2.md)
14. [v0.1.0-rc2 Release Notes](./release-notes-v0.1.0-rc2.md)
15. [v0.1.0-rc1 Release Candidate Checklist](./release-candidate-v0.1.0-rc1.md)
16. [v0.1.0-rc1 Release Notes](./release-notes-v0.1.0-rc1.md)
17. [Development Rules](./development-rules.md)
18. [UI Style Guide](./ui-style-guide.md)
19. [Security Pentest Report v2](./security-pentest-report-v2-2026-04-06.md)
20. [Upload And OCR E2E](./upload-ocr-e2e-2026-04-07.md)
21. [Natural Prompt Pair Testing](./natural-prompt-pair-testing.md)
22. [Natural Prompt Scenario Testing](./natural-prompt-scenario-testing.md)
23. [SharePoint Mock Smoke](./sharepoint-mock-smoke-2026-04-07.md)
24. [Roadmap](./roadmap.md)
25. [Latest Session Handoff](./session-handoff-2026-04-05.md)

## Notes

- The PDF files in this folder are kept as legacy source material.
- The Markdown files are the canonical versions to update going forward.

## Current Project Status

The project now has a real MVP foundation in code, not just in planning.

- Chat works with saved conversations
- Documents can be uploaded, processed, indexed, previewed, and scoped into chat
- Retrieval uses Ollama embeddings and Qdrant with a term-based fallback
- Settings, logs, diagnostics, storage overview, cleanup, and recovery flows exist
- Ubuntu deployment scaffolding now exists alongside Windows-first local development
- A baseline retrieval eval suite now exists to catch quality regressions as the knowledge layer evolves
- Hard retrieval, reply-quality, and broader document-coverage eval suites now exist as well

## What Is Next

The current priority is not broad new platform scope. The current priority is:

1. Keep improving security and admin boundaries without stalling product momentum
2. Keep improving answer quality and retrieval quality
3. Keep expanding eval coverage across more document types and real user questions
4. Keep improving operational reliability and recovery behavior
5. Keep tightening deployment, maintenance, and backup workflows
6. Turn the Ubuntu deploy path into a real first-install Linux server experience
