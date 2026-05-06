# Roadmap

## Project Status - May 6, 2026

Status: MVP hardening on a real Linux server.

The project has moved beyond local-only prototyping. The current live server at
`192.168.1.105` is running the Docker deployment with backend, frontend, Qdrant,
Ollama connectivity, auth, document upload, OCR/indexing, saved chats, and
retrieval over a realistic document library.

Current live baseline:

- backend health: `ok`
- Ollama: `ok`
- Qdrant: `ok`
- uploaded documents: `165`
- processed/indexed documents: `165 / 165`
- failed documents: `0`
- known stuck document: none; `Google cert.pdf` was retried and is now processed/indexed
- document-intelligence stale/background backlog: `0`
- full live conversation suite before the final Swedish/natural-language patch: `26/30`
- focused live regression after the final retrieval patch: `8/8`
- live regression after source workflow, invoice-intelligence, and Writing
  workspace work: `12/12`
- May 6 live validation:
  - system stability: passed
  - invoice document QA: `8/8`
  - document follow-up regression: `11/11`
  - business document QA: `12/12`
  - Writing workspace: `4/4`
  - GitHub fresh install on isolated ports `3100/8100/6433`: passed
  - GitHub update flow after fresh install: passed

Important current caveat:

- the May 6 fixes are committed and pushed to `main`, and the live server is
  aligned to the validated runtime baseline. A safety stash from the earlier
  manual deploy remains on the server, but the working tree is clean.

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

Status: implemented and now in real-library refinement

- Add file upload
- Add text extraction and ingestion pipeline
- Add embeddings and Qdrant integration
- Implement basic RAG over uploaded documents

## Phase 4: Make It Reliable

Status: active current phase, now validated against the live server

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

- keep the GitHub link-install/update smoke in the release-candidate gate
- run the next destructive reinstall only when the server can be safely wiped
- keep improving answer quality on natural business questions across invoices, receipts, contracts, and mixed document libraries
- validate the new document-based draft helpers on real incident, support, and customer-email scenarios
- keep evolving the first Writing workspace from chat templates into a clearer
  report/email drafting workflow if the real incident/customer tests keep
  passing
- keep tightening retrieval ranking, source shaping, and follow-up behavior
- keep improving backup, export, cleanup, and recovery confidence on the live server
- document the server-update flow so deploys do not depend on manual patch copying

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
- retrieval now also handles common natural-language business questions over real invoices better, including:
  - latest uploaded document
  - Swedish invoice-company inventory prompts
  - totals and amounts across invoices
  - ordered products/services across invoice-like documents
  - bike-related purchase searches
  - follow-up questions about the latest referenced document
- invoice intelligence now also supports highest/lowest invoice questions,
  cleaner bullet-list output for multi-invoice/product answers, and line-item
  total fallback when parsed invoice totals are incomplete
- retrieval now keeps named batches and explicit document-name markers scoped
  during product/invoice inventory questions, so a prompt about one upload batch
  does not bleed into unrelated invoice documents
- direct document answers now include structured fallbacks for common business
  lookups such as config/XML port values and explicit invoice identifiers like
  `INV-77`
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

Status: active and materially improved on the live server.

- metadata-backed direct answers now attach sources instead of returning source-less answers
- invoice/product/date/company questions route through document metadata before falling back to broad generation
- Swedish/natural prompts that previously produced "no access to invoices" are now covered by focused regression tests
- remaining work is to reduce noisy broad answers, improve source selection quality, and make latency more predictable

### Phase C: Better Answer Synthesis

- make answers summarize the important result first
- merge overlapping evidence from multiple documents more cleanly
- keep answers natural for both technical and non-technical users
- make uncertainty and conflicting evidence explicit when needed

Status: first writing-assistant path started.

- chat now has draft-helper prompts for customer email, incident report, management summary, and action plan
- these helpers deliberately use the existing document-retrieval layer first, so we can validate answer quality before creating a separate report-writing module
- chat now has a first Writing workspace selector in the composer, so users can
  choose report/email/action-plan output types without manually crafting the
  whole prompt
- action-plan drafting now has a source-grounded structured fallback, so missing
  owners/deadlines are marked as `Unknown` instead of producing a weak refusal
- customer-email drafting now has a source-grounded fallback that still produces
  a usable email skeleton when the source lacks customer-specific detail
- next decision is whether this remains a lightweight chat helper or becomes a dedicated Writing/Reports workspace

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
- live conversation/system check now exists for the deployed AI server
- focused live regression now exists for natural invoice, amount, latest-upload, follow-up, and prompt-injection cases
- live regression now also covers auth remember-me, source-scoped chat,
  duplicate-upload warnings, invoice extremes, invoice follow-up dates, and
  general coding questions staying out of document mode
- May 6 live QA reports now cover system stability, invoice QA, document
  follow-ups, business document questions, and Writing workspace output shape
- next step is to keep growing those suites across more document types, negative cases, and business-style answer checks

### Next

- keep validating the public GitHub install/update path against release-candidate commits
- add a visible operator button for stale document-intelligence refreshes and stuck processing/indexing cases
- keep the live duplicate-upload smoke test in the standard pre-push suite
- expand the live conversation suite with more invoice/product/date questions from the real uploaded library
- add a clearer regression threshold so we can say when a build is good enough to release
- formalize install order, dependency inventory, and setup validation before deeper setup automation
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
