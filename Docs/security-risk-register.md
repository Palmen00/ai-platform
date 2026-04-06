# Security Risk Register

This document is the current security checkpoint for the project.

It is not a formal third-party security audit.
It is an engineering risk register so we can keep improving security while the product grows.

## Current Position

The project is in a good prototype/MVP state, but it is not yet ready for security-classified enterprise documents.

Right now, the biggest gaps are not OCR or retrieval quality. They are:

- no real authentication or authorization
- no encryption-at-rest strategy for uploaded content and metadata
- no tenant isolation or document access boundaries
- operational endpoints that are too open for a hardened deployment
- no explicit secure deployment mode yet

That means we should treat the current system as:

- suitable for controlled local development and internal testing
- not yet suitable for sensitive regulated production use without a security hardening phase

## What Improved Recently

The security posture is better than it was at the start of the prototype phase.

We now have:

- a first admin-auth foundation for sensitive routes
- protected admin surfaces for settings, connectors, logs, cleanup, and backup import/export
- a first `safe mode` that blocks selected risky actions
- a first document-level visibility control through `hidden` documents
- a Security tab in Settings so the current security posture is visible inside the product

This is good progress, but it is still a foundation rather than a finished enterprise model.

## Highest Risks

### Critical

#### Authentication and authorization are only partially implemented

Current state:

- A first admin session model now exists.
- Some sensitive routes are protected.
- There is still no full user model, no real role system beyond admin vs non-admin, and no per-user access boundary.

Relevant files:

- [backend/app/main.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/main.py)
- [backend/app/api/routes/chat.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/api/routes/chat.py)
- [backend/app/api/routes/documents.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/api/routes/documents.py)
- [backend/app/api/routes/system.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/api/routes/system.py)

Risk:

- Sensitive admin areas are better protected now, but ordinary document access is still not tied to real user identities or tenant boundaries.
- The current model is still too thin for production environments where multiple users, departments, or companies will share the system.

Recommended implementation:

- keep the new admin foundation
- add at least:
  - real user accounts or SSO-backed identities
  - role-based access
  - document/library-level access boundaries
  - tenant or workspace boundaries
- keep admin endpoints clearly separated from normal user endpoints

#### No encryption at rest for uploaded documents and metadata

Current state:

- Uploaded files, extracted text, metadata, chunk files, logs, and conversations are stored on disk in plaintext.

Relevant files:

- [backend/app/config.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/config.py)
- [backend/app/services/documents.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/services/documents.py)

Risk:

- If the host is compromised or copied, raw document contents are directly readable.

Recommended implementation:

- use encrypted disks or encrypted host volumes as baseline
- add application-level encryption for the most sensitive artifacts:
  - uploads
  - extracted text
  - conversations
  - export backups
- define a key-management approach before enterprise rollout

#### Export/import path is too permissive for hardened environments

Current state:

- Backup export and import are exposed as backend routes.
- Import can restore runtime settings and conversations.

Relevant file:

- [backend/app/api/routes/system.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/api/routes/system.py)

Risk:

- In a shared or exposed deployment, this is a strong administrative capability without adequate protection.

Recommended implementation:

- admin-only access
- explicit audit logging
- optional full disable in hardened mode
- signed and optionally encrypted backup packages

### High

#### No secure deployment mode yet

Current state:

- The app has one broad runtime posture.
- Prototype-friendly behavior and enterprise-sensitive behavior are not separated.

Risk:

- Useful MVP defaults can become dangerous defaults in real deployments.

Recommended implementation:

- add a `safe mode` / `hardened mode`
- make security-sensitive defaults stricter automatically

#### No tenant isolation

Current state:

- All documents live in one shared local store.
- Conversations and knowledge content are global to the app instance.

Risk:

- This is not safe for multi-company or multi-department hosting.

Recommended implementation:

- introduce tenant or workspace boundaries
- isolate:
  - uploads
  - metadata
  - extracted text
  - vector collections
  - conversations
  - logs

#### Connector secrets are still too environment-oriented

Current state:

- Google Drive and SharePoint credentials are still handled in a prototype-friendly way through environment configuration.
- That is acceptable for local testing, but not the right long-term shape for customer environments.

Risk:

- Harder secret rotation
- Greater operational risk if teams start sharing environment files loosely
- Weak auditability around who connected which source and when

Recommended implementation:

- move connector credential handling toward safer storage
- encrypt persisted tokens/secrets if we store them in app-managed state
- add clear admin-only connector management boundaries
- add audit trails for connector creation, update, and sync

#### Logs may capture sensitive operational details

Current state:

- The app logs chat activity, model usage, and system events.
- Error paths may include raw exception text from dependencies.

Relevant files:

- [backend/app/services/logging_service.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/services/logging_service.py)
- [backend/app/api/routes/chat.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/api/routes/chat.py)
- [backend/app/api/routes/system.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/api/routes/system.py)

Risk:

- Logs can become a secondary source of sensitive data leakage.

Recommended implementation:

- redact sensitive values
- separate audit logs from application/debug logs
- configurable log retention
- disable verbose error detail in hardened environments

### Medium

#### Upload validation is still too permissive

Current state:

- File handling is routed mainly by suffix and content type.
- There is not yet a strict server-side allowlist, content-size policy, or malware scanning stage.

Relevant files:

- [backend/app/api/routes/documents.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/api/routes/documents.py)
- [backend/app/services/document_processing.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/services/document_processing.py)

Risk:

- Unexpected file shapes or oversized files could degrade service or expand attack surface.

Recommended implementation:

- strict server-side allowlist
- max file-size limits by file type
- document count/rate limits
- optional antivirus or malware scan hook before ingest

#### No rate limiting or abuse controls

Current state:

- Chat, upload, and operational endpoints do not appear to have rate limiting or per-client throttling.

Risk:

- Easier denial-of-service or resource exhaustion.

Recommended implementation:

- request throttling
- upload throttling
- background job queue with concurrency limits
- model and OCR concurrency caps

#### CORS is development-friendly, not hardened

Current state:

- CORS is configurable, but the app currently uses a broad development-oriented setup with permissive methods and headers.

Relevant file:

- [backend/app/main.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/main.py)

Recommended implementation:

- environment-specific CORS profiles
- lock allowed origins tightly in production
- separate internal and external deployment profiles

## Safe Mode Proposal

We should add a deployment/runtime profile called `safe mode` or `hardened mode`.

The point is not to make the product unusable. The point is to switch the system from:

- fast, convenient, MVP-friendly defaults

to:

- slower, stricter, safer defaults

### Safe Mode Goals

- reduce accidental data exposure
- reduce attack surface
- make risky features opt-in
- make logging and backups safer
- make deployment behavior more predictable for sensitive customers

### Suggested Safe Mode Behavior

#### Access control

- require authentication
- require admin role for:
  - settings changes
  - cleanup
  - export/import
  - reprocess-all
  - recovery actions

#### Data handling

- require encrypted storage location
- encrypt backup exports
- shorten or redact stored excerpts in logs
- optionally disable storing full extracted text for highly sensitive customers

#### Network posture

- local-only or private-network-only binding by default
- tighter CORS
- no unauthenticated admin routes
- optional block on remote Ollama hosts unless explicitly approved

#### Runtime controls

- disable prototype lanes completely
- disable auto-build behavior for helper images
- stronger upload limits
- lower concurrency for OCR and ingest
- safer background queue behavior

#### Observability

- security audit log
- admin action log
- config change log
- backup/export/import audit trail

### Safe Mode Tradeoff

Safe mode will likely be:

- slower
- stricter
- less convenient
- more predictable and defensible

That is the right trade for customers handling sensitive or security-classified material.

## Good Security Features To Implement Next

Recommended order:

1. role separation beyond the current admin foundation
2. document/library visibility and access controls beyond the first `hidden` flag
3. hardened/admin-only protection for remaining sensitive document mutations
4. upload allowlist plus size/rate limits
5. safe mode runtime profile
6. safer connector secret/token storage
7. encrypted backup/export path
8. tenant/workspace isolation
9. encrypted artifact storage for sensitive deployments
10. audit logging and redaction

## Security-Focused Roadmap Additions

### Near term

- extend the first auth foundation into a clearer role model
- add role-aware route protection
- expand document visibility/access rules beyond the first hidden-document path
- add upload constraints
- add safe mode config surface
- plan safer connector-secret handling

### Mid term

- tenant/workspace isolation
- encrypted exports
- audit log separation
- secure deployment profile for Ubuntu

### Later

- stronger key management
- hardware-backed secrets where available
- optional stricter enterprise deployment blueprint

## Practical Recommendation

If we want this system to handle security-classified company documents, we should treat security as a first-class workstream now.

That does not mean stopping product work.
It means that future architecture decisions should be checked against:

- access control
- data isolation
- encryption
- auditability
- safe defaults

The next concrete engineering step should be:

- design and implement a first `safe mode` configuration layer
- then add authentication and admin-route protection on top of it
