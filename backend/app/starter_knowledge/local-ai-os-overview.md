# Local AI OS Overview

Local AI OS is a self-hosted AI workspace built around:

- local or shared Ollama models
- Qdrant for retrieval
- a FastAPI backend
- a Next.js frontend
- local document ingestion and chat history

Important product areas:

- Chat: ask questions, continue saved conversations, and use retrieved documents when they are relevant.
- Knowledge: upload, preview, reprocess, and manage documents.
- Settings: manage runtime, storage, connectors, users, security, audit, and operations.
- Logs: inspect runtime and audit activity.

How to answer product questions:

- If the user asks about this app, "Local AI OS", "this system", or "Settings", interpret that as this installed product.
- Prefer practical explanations over generic AI theory.
- If a feature depends on uploaded documents or enabled auth, say that clearly.
