# Current Features

## Implemented

### Chat

- Saved conversations with rename and delete
- Cleaner chat-first UI with collapsible sidebar
- Model selection from Ollama chat-capable models
- Retrieval-backed answers with visible sources and retrieval debug
- Document scoping so a chat can be limited to selected files
- Source preview directly inside the chat flow

### Knowledge

- Multi-file upload
- Document processing with extracted text and chunk metadata
- OCR fallback path for scanned PDFs and common image files when OCR is configured in the runtime environment
- Selective `OCRmyPDF` preprocessing for weak or scanned PDFs when Docker is available, with fallback to the existing `Tesseract` path
- Automatic document-type detection such as invoice, contract, insurance, roadmap, architecture, and form-style documents
- Automatic document-date detection so knowledge files can be searched, filtered, and sorted by document date instead of upload date alone
- Automatic company/entity detection for documents such as invoices so questions like supplier-specific invoice searches can be answered from metadata
- Weighted document signal extraction for names, entities, titles, sections, and recurring terms
- Embeddings plus Qdrant indexing
- Reprocess and retry indexing actions
- Search, filter, sort, and preview for uploaded documents
- Focused preview for chunks used in answers
- Server-side pagination, filter, sort, and facet counts for the Knowledge list so larger libraries do not force the browser to do all document work client-side
- Clickable total file count in Knowledge with a file-type breakdown modal
- Hidden-document support as a first security boundary:
  - documents can now be marked as `hidden`
  - hidden documents are filtered out of non-admin Knowledge list and preview flows
  - hidden documents are also filtered out of non-admin retrieval and chat grounding
  - admin users can hide or unhide a document directly from the Knowledge list
- Metadata-aware document search by detected type, detected company/entity, and document date
- Text-like ingestion now supports a much broader set of code and config files, including common `ts`, `tsx`, `js`, `jsx`, `py`, `java`, `cs`, `go`, `rs`, `sql`, `ps1`, `yml`, `yaml`, `toml`, `ini`, `env`, and `xml` files
- The main backend now also supports modern Office-style files as first-class knowledge inputs:
  - `docx`
  - `xlsx`
  - `pptx`
- The document model now also preserves connector-style source metadata so future SharePoint, Google Workspace, OneDrive, or local-folder lanes can feed the same pipeline without inventing a separate storage format
- A first connector manifest and import surface now exists in the backend so external sources can be registered before we build full sync workers
- A first mock/local connector sync lane now exists, so a SharePoint-style library can be simulated from a local folder and imported through the same document pipeline
- A first provider dispatch layer now exists for connectors, with SharePoint as the first named provider behind the generic sync route
- A first SharePoint Graph prototype now exists in backend code, while the recommended testing path still starts with the local/mock SharePoint lane
- A first Google Drive / Google Workspace prototype now also exists in backend code, including native export of Docs, Sheets, and Slides into `docx`, `xlsx`, and `pptx` before they enter the normal pipeline
- SharePoint-style synthetic coverage now includes:
  - a Word runbook
  - a spreadsheet register
  - a rollout slide deck
  - and the current Office/code SharePoint-style suite now verifies those paths at `15/15`
- Detected company/entity metadata is visible in Knowledge previews and participates in Knowledge search
- Detected document signals are visible in Knowledge previews and participate in Knowledge search/matching
- Entity-inventory chat queries such as "Which company appears in a quote?"
- Similar-theme document matching now uses semantic document profiles instead of only raw text overlap
- Synthetic coverage now also includes a SharePoint-style code fixture so we can verify that code-oriented knowledge files are searchable, classifiable, and usable in chat

### Settings And Operations

- Runtime settings editor
- Admin unlock / lock flow for sensitive settings surfaces
- Security tab in Settings showing:
  - auth state
  - auth configuration state
  - safe mode state
  - protected areas
  - planned next security controls
- System diagnostics for backend, Ollama, Qdrant, storage, and recovery
- Logs view with filters and JSON export
- Storage view with cleanable vs persistent areas
- Safe cleanup for cache and logs
- Backup export endpoint and UI download action
- Recovery flow for retriable document indexing failures
- Connector management moved into Settings instead of Knowledge, with:
  - create, edit, enable, disable, delete
  - sync preview / dry run
  - max-files-per-sync limits
  - folder browsing for Google Drive and local-folder lanes
  - local caching in the UI so connector state survives a backend restart more gracefully
- Baseline retrieval eval suite for regression checking
- Hard retrieval eval suite for OCR and document disambiguation
- Reply-quality eval suite for natural document and OCR answers
- Broader document-coverage eval suite across invoice, roadmap, current-features, OCR, and operating-environment documents
- Synthetic business-document eval suite across invoices, contracts, policies, quotes, and incident reports
- Synthetic SharePoint-style Office and code suite now goes `15/15`, including direct content questions for `docx`, `xlsx`, and `pptx`
- Connector routing now supports both SharePoint and Google Drive as named providers behind the same `/connectors/{id}/sync` contract, while local/manual mode remains the easiest way to prototype either provider before live credentials are available
- Coverage now also includes password-cracking document lookup and similar-theme checks when those documents exist locally
- Local preflight script for setup and dependency validation
- Local prototype comparison scripts now exist for `Unstructured` chunking/partitioning and `GLiNER` entity extraction so we can evaluate external open source components before adoption
- A representative `Unstructured` structure eval now scores title and section extraction quality before we consider switching ingestion paths
- A local Ollama-driven document-profile prototype now exists for testing structured summaries, themes, entities, and search clues before we adopt any LLM enrichment path
- A dedicated eval suite now exists for document-profile quality so local Ollama metadata extraction can be measured instead of judged only by inspection
- Current prototype finding: `Unstructured` looks more promising for complex PDFs than for structured `.txt` business documents, so any future adoption will likely need to stay selective instead of replacing the whole ingest path
- Latest split benchmark signal:
  - mixed suite: `1 improved / 4 regressed`
  - PDF-focused suite: `3 improved / 2 regressed`
  - structured-text suite: `0 improved / 3 regressed`
- Current working conclusion: `Unstructured` stays alive as a selective PDF-structure candidate, but it is not a good global replacement for the in-house parser
- Current prototype finding: local Ollama document profiles become much more parseable with JSON-repair, but the semantic quality is still too uneven for main-pipeline adoption without a stronger scoring/normalization layer
- Current prototype finding: `PaddleOCR` installs, but currently fails during inference both on local Windows CPU and in the first Linux Docker benchmark, so it is not a practical candidate yet in our environment
- Current prototype finding: `EasyOCR` runs locally and passes the first OCR comparison suite, but it is noticeably slower than the current path and still needs deeper quality evaluation before any adoption decision
- Current prototype finding: `OCRmyPDF` now has a Docker-based benchmark path and passed the first scanned-PDF suite while also recovering one additional expected term over the current OCR path in the first Swedish school-certificate sample
- Current prototype finding: in the broader mixed OCR suite, `OCRmyPDF` went `5/5` and matched or exceeded the current OCR path on every case we tested, while `EasyOCR` also went `5/5` but did not clearly outperform the current path on the mixed invoice and business-document pages
- Current prototype finding: `Docling` looks promising on cleaner PDFs, but it is too heavy and too unstable on larger manuals and OCR-heavy PDFs in the current Windows development environment, so it is not part of the runtime pipeline
- Current prototype finding: `Marker` is not a good fit for the local baseline. It changed shared dependencies, timed out on simple single-document runs, and left background processes behind after timeout
- Current prototype finding: direct `Surya` OCR is more promising than `Marker` on raw OCR quality, but the first-run model download is large and it also wants dependency versions that conflict with parts of the current prototype stack, so it should stay isolated for now
- The OCR decision is now explicit in `Docs/ocr-decision.md`: keep `OCRmyPDF` as the primary OCR path, keep `Tesseract` as fallback, keep `Surya` isolated, and stop spending mainline effort on weaker OCR candidates for now
- `Knowledge` now records the OCR engine used per processed PDF so we can inspect whether a document was read through native text, `Tesseract`, or `OCRmyPDF`
- `GLiNER` can now be enabled as a cautious entity-enrichment layer during document processing, improving company, organization, and project extraction while existing heuristics remain as fallback
- Retrieval now uses the richer document signal layer more actively, so company names and project names can steer document selection even when they are not matched only by raw excerpt text
- `Unstructured` now has split evaluation coverage:
  - a mixed suite that shows it is not a good global replacement
  - a PDF-focused suite so we can evaluate it fairly on the document-structure problem it is actually trying to solve
  - a text-business suite that makes it explicit where the current in-house parser still wins clearly

### Backend Surface

- `/health`
- `/models`
- `/auth/status`
- `/auth/login`
- `/auth/logout`
- `/chat`
- `/conversations`
- `/documents`
- `/settings`
- `/status`
- `/logs`
- `/cleanup`
- `/export`
- `/connectors`

## Status

The project now has a functional MVP foundation in place with:

- saved chat threads
- semantic retrieval via Ollama embeddings and Qdrant
- grounded answers over uploaded documents
- editable runtime configuration
- logs, diagnostics, cleanup, storage visibility, and recovery tooling
- first real admin/security boundaries around settings, connectors, logs, cleanup, export/import, and hidden documents

## Highest-Priority Next Work

- add a first explicit role model such as `admin` and `viewer`
- decide how connector secrets and tokens should be stored more safely than plain environment configuration
- keep improving answer naturalness and OCR phrasing
- keep reducing duplicate or noisy sources
- expand eval coverage across more document types and business-style questions
- improve deployment, backup, and maintenance confidence
