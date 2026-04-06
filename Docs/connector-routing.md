# Connector Routing

This document defines how external content sources should enter the product.

The goal is to avoid building a separate ingestion system for every provider.

Instead, each connector should do only what is provider-specific:

- authenticate
- list files
- fetch or export file bytes
- provide source metadata

After that, the normal document pipeline should take over.

## Design Rule

Connectors should not own chunking, embeddings, retrieval, or answer logic.

They should only provide:

- file bytes or a local exported file
- original filename
- content type
- source metadata

Then the main pipeline handles:

- storage
- parsing
- OCR if needed
- metadata enrichment
- chunking
- indexing
- retrieval

## Generic Flow

1. Connector authenticates to provider.
2. Connector lists remote items.
3. Connector exports or downloads a supported file.
4. Connector passes the file into the generic connector-ingest path.
5. Document processing continues exactly like a normal uploaded file.

## Source Metadata We Should Preserve

Every connector-imported document should be able to retain:

- `source_origin`
- `source_provider`
- `source_uri`
- `source_container`
- `source_last_modified_at`

That gives us enough information later for:

- deduplication
- incremental sync
- re-import decisions
- provider-aware filtering
- better auditability

## Provider Mapping

### SharePoint

Connector responsibilities:

- authenticate to Microsoft Graph or SharePoint APIs
- enumerate libraries/folders/files
- export Office files where needed
- fetch file bytes
- preserve:
  - site/library/folder info
  - remote URI
  - remote modified timestamp

### Google Workspace

Connector responsibilities:

- authenticate to Google Drive APIs
- export native Docs/Sheets/Slides into usable file formats
- fetch file bytes
- preserve:
  - Drive file id
  - folder/container
  - remote URI
  - remote modified timestamp

### OneDrive

Connector responsibilities:

- authenticate
- enumerate files
- fetch file bytes
- preserve remote metadata

### Local Folder / Network Share

Connector responsibilities:

- enumerate files
- track local path or share path
- preserve last modified timestamp

## Recommended File Routing

Once a connector has produced a real file, it should follow the same routing rules as uploads:

- scanned PDF -> `OCRmyPDF` then `Tesseract` fallback
- image -> OCR path
- `docx` -> Word parser
- `xlsx` -> spreadsheet parser
- `pptx` -> presentation parser
- code/config/text -> text-like parser

## Current Foundation In Code

The repo now has a generic connector-ingest foundation:

- document metadata supports source metadata fields
- the main document service can import external files
- a generic connector ingest service exists for future connectors

Relevant files:

- [backend/app/schemas/document.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/schemas/document.py)
- [backend/app/schemas/connector.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/schemas/connector.py)
- [backend/app/services/documents.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/services/documents.py)
- [backend/app/services/connector_ingest.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/services/connector_ingest.py)
- [backend/app/services/connector_registry.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/services/connector_registry.py)
- [backend/app/api/routes/connectors.py](c:/Users/oskar/OneDrive/Desktop/AI%20Platform/backend/app/api/routes/connectors.py)

## Connector Manifest Layer

The repo now also has a lightweight connector manifest layer.

It is intentionally small and provider-agnostic.

Each connector can now store:

- name
- provider
- enabled state
- auth mode
- root path
- container/library/folder label
- include patterns
- exclude patterns
- preferred export formats
- provider-specific settings
- notes
- last sync timestamp

This is not a full sync engine yet.
It is the configuration contract we can use before we build real connector workers.

## Current API Surface

The backend now exposes a first connector management surface:

- `GET /connectors`
- `POST /connectors`
- `GET /connectors/{id}`
- `PUT /connectors/{id}`
- `DELETE /connectors/{id}`
- `POST /connectors/{id}/sync`
- `POST /connectors/{id}/import-file`
- `POST /connectors/{id}/sync-local`

That last endpoint is mainly a prototype bridge right now:

- a future connector can fetch/export a real file
- then pass it into the main document pipeline through the connector import path

The generic sync route is now the main provider entrypoint.

Today, SharePoint is the first provider behind that route.

For now it still uses a mock/local library path, but the important architectural step is that provider dispatch now exists and future real API logic can sit behind the same `sync` contract.

The local sync behavior is the first mock connector lane:

- it reads from a local root folder
- applies include/exclude patterns from the manifest
- generates stable provider-style source URIs
- imports or updates matching files through the normal document pipeline
- tracks imported, updated, and skipped files

## Mock SharePoint Prototype

The current recommended first prototype is:

- provider: `sharepoint`
- auth mode: `mock`, `manual`, or `local`
- root path: a local folder that represents a SharePoint library export
- container: something like `Team Docs`

That lets us test:

- manifest structure
- file discovery
- source metadata
- incremental sync behavior
- ingestion and retrieval quality

without needing a real SharePoint tenant yet.

## Provider Dispatch

The codebase now has a real provider dispatch layer.

Today:

- `sharepoint` -> provider-specific SharePoint service
- `google_drive` / `google_workspace` / `gdrive` / `google` -> provider-specific Google Drive service
- `local` / `filesystem` / `folder` -> generic local sync path

This means the next real SharePoint step is no longer “invent a connector system”.
It is simply:

- replace mock/local SharePoint sync with Graph-backed list/export logic
- keep the rest of the pipeline unchanged

## SharePoint Graph Prototype

The SharePoint provider now has a first Graph-backed lane in code.

Current supported auth mode:

- `graph`
- `graph_client_credentials`
- `client_credentials`

Current required environment variables:

- `SHAREPOINT_TENANT_ID`
- `SHAREPOINT_CLIENT_ID`
- `SHAREPOINT_CLIENT_SECRET`

Current required connector `provider_settings`:

- `drive_id`

Current optional connector `provider_settings`:

- `folder_path`

Current Graph behavior:

- obtain a client-credentials access token
- list files from a drive root or folder path
- recurse through folders
- download files
- pass them into the same document pipeline through external upsert/import

This is still a prototype layer.
What it does not do yet:

- tenant/site discovery flows
- interactive auth
- token refresh UX
- delta sync
- deleted-file reconciliation
- Graph-specific admin UI

## Google Drive / Workspace Prototype

The connector layer now also has a first Google Drive / Workspace provider in code.

Current supported auth modes:

- `mock`
- `manual`
- `local`
- `drive`
- `google_drive`
- `google_workspace`
- `oauth_refresh_token`
- `refresh_token`

Current recommended testing path:

- use `provider=google_drive`
- use `auth_mode=manual` or `local`
- point `root_path` at a local folder that simulates a Drive export

Current required environment variables for live Drive sync:

- `GOOGLE_DRIVE_CLIENT_ID`
- `GOOGLE_DRIVE_CLIENT_SECRET`
- `GOOGLE_DRIVE_REFRESH_TOKEN`

Current optional environment variables:

- `GOOGLE_DRIVE_API_BASE_URL`
- `GOOGLE_DRIVE_TOKEN_URL`

Current optional connector `provider_settings`:

- `folder_id`
- `drive_id`

Current Google behavior:

- obtain an access token from a refresh token
- list supported files recursively in Drive or a selected folder
- export native Google Docs/Sheets/Slides into:
  - `docx`
  - `xlsx`
  - `pptx`
- download normal Drive files directly
- pass the resulting files into the same external ingest path as uploads and SharePoint

What it does not do yet:

- interactive OAuth setup UX
- automatic Drive discovery
- delta sync
- deleted-file reconciliation
- Drive-specific admin UI
- source-aware filtering in the frontend

## What Comes Next

Recommended next steps:

1. add one first real provider prototype:
   - SharePoint
   - or Google Workspace
2. keep sync incremental instead of always importing everything
3. add source-aware UI visibility in Knowledge
4. add source-aware filters in retrieval and admin tooling
5. later add real provider auth and export logic behind the same manifest/sync contract
