from __future__ import annotations

from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path

from app.schemas.connector import ConnectorBrowseResponse
from app.schemas.connector import ConnectorFolderOption
from app.schemas.connector import ConnectorManifest
from app.schemas.connector import ConnectorSyncResponse
from app.schemas.connector import ConnectorSyncResult
from app.services.documents import DocumentService


class ConnectorSyncService:
    BROWSE_FOLDER_LIMIT = 200
    SUPPORTED_EXTENSIONS = {
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".tif",
        ".tiff",
        ".webp",
        ".docx",
        ".xlsx",
        ".pptx",
        ".txt",
        ".text",
        ".log",
        ".rst",
        ".md",
        ".markdown",
        ".mdx",
        ".json",
        ".jsonl",
        ".ndjson",
        ".csv",
        ".tsv",
        ".yml",
        ".yaml",
        ".toml",
        ".ini",
        ".cfg",
        ".conf",
        ".env",
        ".properties",
        ".xml",
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".java",
        ".cs",
        ".go",
        ".rs",
        ".php",
        ".rb",
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".h",
        ".hpp",
        ".swift",
        ".kt",
        ".kts",
        ".scala",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".psm1",
        ".psd1",
        ".sql",
        ".html",
        ".htm",
        ".css",
        ".scss",
        ".less",
        ".vue",
        ".svelte",
    }

    def __init__(self) -> None:
        self.document_service = DocumentService()

    def sync_local_connector(
        self,
        connector: ConnectorManifest,
        *,
        dry_run: bool = False,
    ) -> ConnectorSyncResponse:
        if not connector.root_path:
            raise ValueError("Connector root_path is required for local sync.")

        root_path = Path(connector.root_path)
        if not root_path.exists() or not root_path.is_dir():
            raise FileNotFoundError(f"Connector root path not found: {root_path}")

        scanned_count = 0
        imported_count = 0
        updated_count = 0
        skipped_count = 0
        results: list[ConnectorSyncResult] = []
        max_files = self._max_files_limit(connector)

        for file_path in sorted(root_path.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                continue

            relative_path = file_path.relative_to(root_path).as_posix()
            if not self._matches_patterns(relative_path, connector.include_patterns, default=True):
                continue
            if self._matches_patterns(relative_path, connector.exclude_patterns, default=False):
                continue

            if max_files is not None and len(results) >= max_files:
                break

            scanned_count += 1
            source_uri = self._build_mock_source_uri(connector, relative_path)
            source_last_modified_at = datetime.fromtimestamp(
                file_path.stat().st_mtime,
                tz=UTC,
            ).isoformat()

            if dry_run:
                action, document_id = self.document_service.predict_external_document_action(
                    source_provider=connector.provider,
                    source_uri=source_uri,
                    source_last_modified_at=source_last_modified_at,
                )
            else:
                try:
                    document, action = self.document_service.upsert_external_document(
                        file_path=file_path,
                        original_name=file_path.name,
                        content_type=self.document_service._guess_content_type(file_path),
                        source_connector_id=connector.id,
                        source_provider=connector.provider,
                        source_uri=source_uri,
                        source_container=connector.container or connector.name,
                        source_last_modified_at=source_last_modified_at,
                        visibility=connector.document_visibility,
                        access_usernames=connector.access_usernames,
                    )
                except ValueError:
                    document_id = None
                    action = "skipped"
                    skipped_count += 1
                else:
                    document_id = document.id

                    if action == "imported":
                        imported_count += 1
                        self.document_service.process_document(document.id)
                    elif action == "updated":
                        updated_count += 1
                        self.document_service.process_document(document.id)
                    else:
                        skipped_count += 1

            if dry_run:
                if action == "imported":
                    imported_count += 1
                elif action == "updated":
                    updated_count += 1
                else:
                    skipped_count += 1

            results.append(
                ConnectorSyncResult(
                    document_id=document_id,
                    original_name=file_path.name,
                    source_uri=source_uri,
                    action=f"would_{action}" if dry_run else action,
                )
            )

        return ConnectorSyncResponse(
            connector_id=connector.id,
            dry_run=dry_run,
            scanned_count=scanned_count,
            imported_count=imported_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            results=results,
        )

    def browse_local_connector(self, connector: ConnectorManifest) -> ConnectorBrowseResponse:
        if not connector.root_path:
            raise ValueError("Connector root_path is required for local browsing.")

        root_path = Path(connector.root_path)
        if not root_path.exists() or not root_path.is_dir():
            raise FileNotFoundError(f"Connector root path not found: {root_path}")

        folders = [
            ConnectorFolderOption(
                id=str(root_path),
                name=root_path.name or str(root_path),
                path=str(root_path),
                provider=connector.provider,
            )
        ]

        for folder_path in sorted(
            (path for path in root_path.iterdir() if path.is_dir()),
            key=lambda path: path.as_posix().lower(),
        ):
            folders.append(
                ConnectorFolderOption(
                    id=str(folder_path),
                    name=folder_path.name,
                    path=str(folder_path),
                    provider=connector.provider,
                )
            )

        return ConnectorBrowseResponse(
            provider=connector.provider,
            folders=folders,
        )

    def _matches_patterns(
        self,
        relative_path: str,
        patterns: list[str],
        *,
        default: bool,
    ) -> bool:
        if not patterns:
            return default
        lowered = relative_path.lower()
        return any(fnmatch(lowered, pattern.lower()) for pattern in patterns)

    def _build_mock_source_uri(
        self,
        connector: ConnectorManifest,
        relative_path: str,
    ) -> str:
        container = (connector.container or connector.name or "library").strip().replace(" ", "-")
        return f"{connector.provider}://{container}/{relative_path}"

    def _max_files_limit(self, connector: ConnectorManifest) -> int | None:
        raw_value = (connector.provider_settings.get("max_files") or "").strip()
        if not raw_value:
            return None

        try:
            parsed = int(raw_value)
        except ValueError:
            return None

        return parsed if parsed > 0 else None
