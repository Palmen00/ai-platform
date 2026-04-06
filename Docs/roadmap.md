# Roadmap

## Phase 1: Foundation

Status: mostly complete

- Define a single primary use case: private internal document chat
- Lock the MVP scope and reject non-essential platform features
- Set up repository, local development flow, and deployment baseline
- Formalize Windows as the dev environment and Ubuntu 24 as the deployment target
- Establish backend and frontend skeletons
- Add core auth and service wiring
- Define persistent data directories and cleanup boundaries early

## Phase 2: Core User Flow

Status: largely complete in development

- Build onboarding flow
- Implement model discovery and simple model recommendation
- Build chat UI and chat API
- Add system health and status visibility
- Keep local Windows usage lightweight and avoid creating a second full product path

## Phase 3: Knowledge Layer

Status: implemented and now in refinement

- Add file upload
- Add text extraction and ingestion pipeline
- Add embeddings and Qdrant integration
- Implement basic RAG over uploaded documents

## Phase 4: Make It Reliable

Status: active current phase

- Improve answer quality and retrieval behavior
- Tighten UX around failures, loading states, and empty states
- Build a minimal dashboard or admin view
- Test installation and operation on realistic hardware setups
- Add explicit start, stop, update, and cleanup flows
- Ensure updates do not leave behind uncontrolled storage growth
- Keep moving dev-only configuration flows toward product-style setup, especially for connectors and security boundaries

## Outcome

Deliver a working MVP for a self-hosted private knowledge assistant.

## Phase 5: Expansion After MVP

Status: intentionally deferred

Only after the core workflow is stable:

- Add offline knowledge packs such as Kiwix sources
- Add selected connectors with real demand
- Explore advanced routing and agent behavior
- Expand administration and enterprise features

## Current Recommended Sequence

### Now

- improve answer quality and grounded response quality
- improve retrieval ranking and source shaping
- improve backup, export, cleanup, and recovery confidence
- tighten Ubuntu deployment and operational documentation
- define the first Linux server installer/bootstrap scope so a new server can reach a stable LLM deployment with minimal manual setup

## Reliability Track For Large Document Sets

This track is now a core product priority because answer trust is what determines whether teams continue using the system.

### Phase A: Better Document Structure

- extract cleaner text from different document types
- preserve more document structure during ingest
- improve chunking so sections and headings are respected better
- attach more useful metadata to documents and chunks
- build a clearer per-file-type routing strategy so PDF, image, text, code, config, and later Office/SharePoint content can each use the right extraction path

Progress now includes:

- document type detection for common business and product documents
- document date extraction for invoices, contracts, insurance, and similar files
- company/entity detection for supplier-aware document filtering and invoice lookups
- weighted signal extraction for names, entities, headings, titles, and recurring terms
- knowledge-layer filtering and sorting based on that metadata
- metadata-aware retrieval so document type, supplier/entity, and date can guide document selection in chat
- broader text-like ingestion coverage for code and config files so repository content and future SharePoint exports can be indexed without pretending they are PDFs
- first-class support for modern Office-style documents is now part of the main path for `docx`, `xlsx`, and `pptx`, and the current synthetic SharePoint-style suite is green for Word, spreadsheet, presentation, and code cases; the larger SharePoint-routing milestone still needs broader real-world metadata and connector behavior across mixed file libraries
- a first generic connector-ingest foundation now exists so future SharePoint/Google Workspace connectors can feed the same storage and processing pipeline instead of creating a second ingestion system
- broader entity-inventory queries such as asking which company appears in a quote or contract
- synthetic business-document eval coverage for invoices, contracts, policies, quotes, and incident reports
- semantic document-profile matching for "similar theme" questions, with conversation-history fallback for follow-up prompts
- local prototype track for `Unstructured` and `GLiNER` so ingestion and entity extraction can be compared against the in-house pipeline before adoption
- local prototype track for `Docling` so PDF structure extraction can be compared against the in-house pipeline before adoption
- local prototype track for LLM-driven document profiles so Ollama can be tested as a metadata-enrichment layer before any runtime integration
- first cautious `GLiNER` enrichment is now available behind configuration so we can improve entities incrementally without replacing the existing extraction path all at once
- retrieval now starts benefiting from those richer signals as well, but bulk backfill of old metadata remains explicit rather than automatic so large libraries do not stall during normal browsing
- a representative `Unstructured` structure-eval suite now exists so title and section extraction can be measured before we adopt any new partitioning path
- current `Unstructured` prototype results suggest the likely adoption target is PDF-heavy documents first, not structured `.txt` business documents where the in-house section logic currently performs better
- the latest split `Unstructured` benchmark keeps reinforcing that: the PDF-focused suite is promising enough to keep exploring, while the structured-text suite remains clearly worse than the in-house parser
- a document-profile eval suite now exists so local Ollama metadata enrichment can be measured for quality before any ingestion integration decision
- current document-profile results suggest the path is promising for enrichment, but not yet consistent enough for direct ingest adoption without stronger normalization, scoring, and validation
- the OCR prototype track now includes `PaddleOCR`, `EasyOCR`, and `OCRmyPDF`, with `PaddleOCR` currently blocked by runtime failures in both local Windows and first Linux Docker testing, `EasyOCR` looking usable for local comparisons, and `OCRmyPDF` looking promising as a scanned-PDF preprocessing building block
- the current `Docling` prototype result is that it looks useful on cleaner PDFs but is too memory-heavy and unstable on larger/manual and OCR-heavy PDFs in the current Windows dev environment, so it should remain prototype-only unless a selective server-side use case proves out
- the current `Marker` prototype result is that it is not worth pulling forward, because it adds too much install/runtime friction without enough quality upside in our local baseline
- the current `Surya` prototype result is more encouraging on OCR quality than `Marker`, but it still belongs in an isolated prototype lane until we decide whether it makes sense in a cleaner server-side or dedicated OCR environment
- the OCR decision is now explicit: `OCRmyPDF` stays as the primary OCR engine, `Tesseract` stays as fallback, and OCR experiments should remain prototype-only unless they clearly beat that combination
- the next OCR prototype milestone is to benchmark `OCRmyPDF` against more real scanned PDFs and then, if the broader suite keeps holding, move it into a selective opt-in preprocessing path instead of replacing the whole OCR pipeline at once
- that selective `OCRmyPDF` preprocessing path has now started landing in the main backend for scanned/weak PDFs, while the default OCR path still falls back to `Tesseract` when needed
- the OCR prototype track now also includes `OCRmyPDF` benchmarking in Docker so we can evaluate scanned-PDF preprocessing as a lighter building block instead of only testing full OCR-engine replacements
- the next document-structure milestone is to evaluate `Unstructured` as a selective PDF-heavy parsing path rather than treating it as a global replacement for structured text documents
- Google Drive is now working as a live connector lane, and connector UX has reached a first product-like state with:
  - create/edit/delete
  - dry-run preview
  - max-files-per-sync
  - folder picking
  - connector status inside Settings
- the next connector milestone is to replace more of the `.env`-style prototype setup with safer token/secret handling and clearer source-scoping for real customers

### Phase B: Better Retrieval And Ranking

- improve hybrid retrieval quality across larger document sets
- prioritize explicitly referenced documents more strongly
- add stronger reranking and source filtering
- reduce weak or redundant supporting sources

### Phase C: Better Answer Synthesis

- make answers summarize the important result first
- merge overlapping evidence from multiple documents more cleanly
- keep answers natural for both technical and non-technical users
- make uncertainty and conflicting evidence explicit when needed

### Phase D: Evaluation And Reliability Checks

- define test questions and expected answers
- measure whether the correct documents are retrieved
- measure whether answers are correct, complete, and grounded
- use those evaluations to catch regressions as the system grows

Status: started

- baseline retrieval eval suite now exists in the repo
- OCR and document-disambiguation hard suite now exists in the repo
- reply-quality suite now exists for natural document and OCR answers
- broader document-coverage suite now exists for invoice, roadmap, current-features, OCR, and operating-environment questions
- next step is to keep growing those suites across more document types, negative cases, and business-style answer checks

### Next

- formalize install order, dependency inventory, and setup validation before deeper setup automation
- turn the current Ubuntu deployment lane into an installer-oriented bootstrap flow for blank servers
- compare `Unstructured` and `GLiNER` against more real document categories before replacing parts of the current pipeline
- keep `Unstructured` focused on PDF-structure evaluation first, because the current mixed suite already shows it is weaker than the in-house parser on structured `.txt` business documents
- add light automation such as watch-folder ingest or safer background retries
- continue UX polish where it improves clarity and trust
- start a dedicated security hardening track:
  - roles and document visibility
  - admin-route protection
  - upload constraints
  - safe mode / hardened mode
  - encrypted backup/export path
  - move connector secrets from app-managed encryption toward stronger host or secret-manager integration
  - clearer audit boundaries for admin actions

### Later

- offline knowledge packs
- selected connectors
- broader enterprise features
- agent-like workflows
