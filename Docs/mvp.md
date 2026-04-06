# MVP

## Goal

Make private document-based AI easy to install and useful on day one.

## Primary User Outcome

A small team or internal IT owner should be able to install the product, select a recommended model, upload documents, and start asking useful questions through a clean web UI.

## In Scope

- Linux installation flow for Ubuntu or Debian
- Ubuntu 24 as the primary deployment target
- Guided setup with sensible defaults
- Ollama integration
- Model selection with simple performance-oriented recommendations
- Authentication
- Basic admin or status view
- Chat UI
- Dark mode support
- Frontend theming support without hardcoded design tokens in components
- UI text structured so multiple languages can be added later
- Fonts managed centrally so typography can be changed without broad refactors
- Centralized configuration for UI tokens, branding, and other values that are expected to evolve
- Document upload
- Document ingestion and chunking
- Basic RAG with Qdrant
- Clear error states and health visibility
- Clear storage layout and cleanup behavior for updates and rebuilds

## Out of Scope

- Agents
- Agent marketplace
- Workflow automation
- Offline wiki packs and Stack Overflow style knowledge bundles
- SharePoint and other complex enterprise connectors
- Advanced routing between many tools or backends
- Multi-tenant support
- Fine-grained enterprise administration
- Broad plugin or module systems

## Success Criteria

The MVP is successful when a user can:

- Complete installation without hand-assembling the stack
- Start the web UI and log in
- Select a model appropriate for the machine
- Upload documents successfully
- Ask questions and receive grounded answers from those documents
- Understand system status when something fails
- Update or redeploy the system without creating uncontrolled storage growth

## Environment Assumptions

- Development happens primarily on Windows
- Production-style deployment targets Ubuntu 24
- Local Windows use is supported for development and lightweight testing, not as a separate first-phase desktop product

## Non-Goals

The MVP is not trying to be a complete AI platform. It is trying to prove a tight and valuable workflow that can later support broader platform features.

Full multi-language coverage is not required in the first release, but the frontend must be built so language expansion is straightforward.

## Current MVP Status

The MVP is now partially implemented and usable in development.

### Working Now

- Chat with saved conversations
- Ollama model discovery and selection
- Document upload and processing
- Chunking, embeddings, and Qdrant indexing
- Retrieval-backed answers with sources
- Document preview and document scoping in chat
- Settings, diagnostics, logs, storage visibility, cleanup, and recovery tools
- Windows development flow and Ubuntu deployment scaffolding

### Still Missing Or Incomplete

- authentication
- onboarding and setup wizard
- model recommendation UX
- richer deployment and backup/import flows
- further retrieval quality improvements
- broader polish for production-style installation

## Current Definition Of Done

The next MVP checkpoint should be considered complete when:

- the install -> upload -> chat workflow feels stable and predictable
- grounded answers are consistently understandable and useful
- document retrieval quality is good enough for repeated real usage
- deployment, cleanup, and recovery feel safe and understandable
