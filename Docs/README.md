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
12. [Development Rules](./development-rules.md)
13. [Roadmap](./roadmap.md)
14. [Latest Session Handoff](./session-handoff-2026-04-05.md)

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
