# Architecture

## System Overview

The platform is organized into three main layers:

1. Frontend: Next.js web UI
2. Backend: FastAPI API layer
3. AI layer: Ollama running on a Linux VM

Primary request flow:

`User -> Frontend -> Backend -> Ollama -> Response -> UI`

## Responsibilities By Layer

### Frontend

- Handles user interaction and navigation
- Presents chat, knowledge, and settings interfaces
- Calls backend APIs for health, models, runtime settings, chat, and knowledge features

### Backend

- Routes requests between frontend and AI services
- Manages model-related operations
- Exposes editable runtime configuration for supported AI and retrieval settings
- Separates chat orchestration, retrieval, and generation into distinct services
- Persists conversation threads separately from document storage
- Serves as the integration point for future RAG and agent capabilities

Current backend flow is intentionally split into:

- Route layer: HTTP endpoints and response handling
- Conversation layer: saved chat threads and metadata
- Retrieval layer: document lookup over processed chunks
- Generation layer: prompt building and model calls
- Orchestration layer: combines retrieval and generation into a chat response

### AI Layer

- Runs local models through Ollama
- Provides inference on a dedicated Linux environment

## Code Architecture Principles

- Keep frontend code modular with separated features and components
- Keep backend code modular with clear separation between routes and business logic
- Separate UI, logic, and data handling
- Preserve scalability and maintainability as the system grows

## Development Topology

- Develop locally on Windows
- Run frontend and backend as separate processes during development
- Allow local development against services running on the Windows machine
- Deploy the full stack to Ubuntu 24 later

## Environment Strategy

- Windows is the primary development environment
- Ubuntu 24 is the primary deployment target
- Local single-user use on Windows is useful for development and testing
- Full Windows desktop product support is not a first-phase requirement

This keeps the MVP focused while still allowing the system to be used locally during development.

## Deployment Direction

The current architecture is aimed at local development first, followed by a Linux deployment model on Ubuntu 24. Docker and an install script are the intended path for packaging and repeatable setup.

## Storage And Cleanup Principles

- Keep application code separate from persistent data
- Use a clear project data layout for uploads, vector data, logs, cache, and temporary files
- Do not duplicate model files across deploys or app versions
- Reuse existing Ollama-managed models instead of bundling models into application releases
- Make cleanup an explicit part of deployment and update workflows

Expected operational flows should include:

- Start
- Stop
- Update
- Cleanup

Cleanup must be able to remove old build artifacts, temporary files, stale caches, and replaced deploy assets without risking active user data or shared model storage.

## Current Implementation Status

The current codebase already reflects most of this architecture in practice.

- frontend includes chat, knowledge, settings, logs, and shared shell/navigation
- backend is split into routes, conversations, retrieval, generation, orchestration, maintenance, and diagnostics services
- document processing, chunk storage, extracted text storage, and vector indexing are separated
- runtime settings, storage inspection, cleanup, and recovery are exposed through the backend

## Current Architectural Priorities

- keep retrieval and generation boundaries clean
- avoid collapsing chat, retrieval, preview, and operations back into large files
- improve deployment and maintenance without changing the core architecture unnecessarily
- keep Windows development simple while treating Ubuntu as the primary operational target

## Near-Term Architecture Work

- improve retrieval ranking and source shaping
- strengthen backup/export and future import paths
- add light operational automation without creating a large agent framework
