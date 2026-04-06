# Tech Stack

## Core Stack

- Backend: FastAPI
- Frontend: React / Next.js
- AI engine: Ollama
- Vector database: Qdrant
- Database: SQLite or PostgreSQL
- Authentication: JWT or session-based auth
- Reverse proxy: Nginx or Caddy
- Deployment: Docker Compose

## Why Docker

- Easier installation
- Clear service boundaries
- Portable deployment
- Better path to scaling later

## Current Stack Status

The current implementation is effectively:

- Backend: FastAPI
- Frontend: Next.js App Router
- AI engine: Ollama
- Embeddings: Ollama embedding model
- Vector database: Qdrant
- OCR fallback: PyMuPDF + pytesseract + Tesseract OCR engine for scanned PDFs
- Local persistence: file-based storage for documents, metadata, chunks, extracted text, logs, and conversations
- Deployment path: Docker Compose for Ubuntu deployment, local process-based development on Windows

## Near-Term Stack Work

- keep Docker deployment aligned with the current app structure
- improve backup and restore around local file-based persistence
- keep runtime configuration explicit and easy to inspect
- postpone adding extra infrastructure until the current stack feels production-ready
