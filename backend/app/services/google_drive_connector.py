from __future__ import annotations

from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.schemas.connector import ConnectorBrowseResponse
from app.schemas.connector import ConnectorFolderOption
from app.schemas.connector import ConnectorManifest
from app.schemas.connector import ConnectorSyncResponse
from app.schemas.connector import ConnectorSyncResult
from app.services.connector_sync import ConnectorSyncService
from app.services.documents import DocumentService


class GoogleDriveConnectorService:
    """Provider-specific Google Drive / Workspace connector.

    Current modes:
    - mock/manual/local: use local folder sync to simulate a Drive folder
    - drive/oauth_refresh_token/refresh_token: use Google Drive APIs
    """

    GOOGLE_NATIVE_EXPORTS = {
        "application/vnd.google-apps.document": (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".docx",
        ),
        "application/vnd.google-apps.spreadsheet": (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xlsx",
        ),
        "application/vnd.google-apps.presentation": (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".pptx",
        ),
        "application/vnd.google-apps.drawing": ("application/pdf", ".pdf"),
    }

    def __init__(self) -> None:
        self.local_sync = ConnectorSyncService()
        self.document_service = DocumentService()

    def supports(self, connector: ConnectorManifest) -> bool:
        provider = (connector.provider or "").strip().lower()
        return provider in {"google_drive", "google_workspace", "gdrive", "google"}

    def sync(
        self,
        connector: ConnectorManifest,
        *,
        dry_run: bool = False,
    ) -> ConnectorSyncResponse:
        auth_mode = (connector.auth_mode or "manual").strip().lower()
        if auth_mode in {"mock", "manual", "local"}:
            return self.local_sync.sync_local_connector(connector, dry_run=dry_run)
        if auth_mode in {
            "drive",
            "google_drive",
            "google_workspace",
            "oauth_refresh_token",
            "refresh_token",
        }:
            return self._sync_drive_connector(connector, dry_run=dry_run)

        raise ValueError(
            f"Unsupported Google Drive auth_mode '{connector.auth_mode}'."
        )

    def browse(self, connector: ConnectorManifest) -> ConnectorBrowseResponse:
        auth_mode = (connector.auth_mode or "manual").strip().lower()
        if auth_mode in {"mock", "manual", "local"} and connector.root_path:
            return self.local_sync.browse_local_connector(connector)
        if auth_mode in {
            "drive",
            "google_drive",
            "google_workspace",
            "oauth_refresh_token",
            "refresh_token",
        }:
            return self._browse_drive_connector(connector)

        raise ValueError(
            f"Unsupported Google Drive auth_mode '{connector.auth_mode}'."
        )

    def _sync_drive_connector(
        self,
        connector: ConnectorManifest,
        *,
        dry_run: bool = False,
    ) -> ConnectorSyncResponse:
        client_id = settings.google_drive_client_id
        client_secret = settings.google_drive_client_secret
        refresh_token = settings.google_drive_refresh_token
        if not client_id or not client_secret or not refresh_token:
            raise ValueError(
                "Google Drive sync requires GOOGLE_DRIVE_CLIENT_ID, "
                "GOOGLE_DRIVE_CLIENT_SECRET, and GOOGLE_DRIVE_REFRESH_TOKEN."
            )

        access_token = self._get_drive_access_token(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
        )
        folder_id = connector.provider_settings.get("folder_id", "").strip()
        drive_id = connector.provider_settings.get("drive_id", "").strip()

        scanned_count = 0
        imported_count = 0
        updated_count = 0
        skipped_count = 0
        results: list[ConnectorSyncResult] = []
        max_files = self.local_sync._max_files_limit(connector)

        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            for remote_file in self._list_drive_files(
                access_token=access_token,
                folder_id=folder_id,
                drive_id=drive_id,
            ):
                relative_path = remote_file["relative_path"]
                if not self._matches_patterns(relative_path, connector.include_patterns, default=True):
                    continue
                if self._matches_patterns(relative_path, connector.exclude_patterns, default=False):
                    continue

                if max_files is not None and len(results) >= max_files:
                    break

                scanned_count += 1
                if dry_run:
                    action, document_id = self.document_service.predict_external_document_action(
                        source_provider=connector.provider,
                        source_uri=remote_file["source_uri"],
                        source_last_modified_at=remote_file["last_modified_at"],
                    )
                else:
                    local_name = remote_file["local_name"]
                    local_path = temp_root / Path(remote_file["relative_path"])
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    self._download_drive_file(
                        remote_file=remote_file,
                        access_token=access_token,
                        target_path=local_path,
                    )
                    try:
                        document, action = self.document_service.upsert_external_document(
                            file_path=local_path,
                            original_name=local_name,
                            content_type=remote_file["content_type"],
                            source_connector_id=connector.id,
                            source_provider=connector.provider,
                            source_uri=remote_file["source_uri"],
                            source_container=connector.container or connector.name,
                            source_last_modified_at=remote_file["last_modified_at"],
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
                        original_name=remote_file["local_name"],
                        source_uri=remote_file["source_uri"],
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

    def _browse_drive_connector(self, connector: ConnectorManifest) -> ConnectorBrowseResponse:
        client_id = settings.google_drive_client_id
        client_secret = settings.google_drive_client_secret
        refresh_token = settings.google_drive_refresh_token
        if not client_id or not client_secret or not refresh_token:
            raise ValueError(
                "Google Drive browsing requires GOOGLE_DRIVE_CLIENT_ID, "
                "GOOGLE_DRIVE_CLIENT_SECRET, and GOOGLE_DRIVE_REFRESH_TOKEN."
            )

        access_token = self._get_drive_access_token(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
        )
        folder_id = connector.provider_settings.get("folder_id", "").strip()
        drive_id = connector.provider_settings.get("drive_id", "").strip()
        root_folder_id = folder_id or "root"
        root_label = connector.container or connector.name or "Google Drive Root"
        headers = {"Authorization": f"Bearer {access_token}"}
        folders = [
            ConnectorFolderOption(
                id=root_folder_id,
                name=root_label,
                path="/",
                provider=connector.provider,
            )
        ]
        next_page_token = ""

        while True:
            request_params: dict[str, str] = {
                "q": (
                    "trashed = false and "
                    f"'{root_folder_id}' in parents and "
                    "mimeType = 'application/vnd.google-apps.folder'"
                ),
                "fields": "nextPageToken,files(id,name,mimeType)",
                "pageSize": str(self.local_sync.BROWSE_FOLDER_LIMIT),
                "includeItemsFromAllDrives": "true",
                "supportsAllDrives": "true",
            }
            if drive_id:
                request_params["corpora"] = "drive"
                request_params["driveId"] = drive_id
            if next_page_token:
                request_params["pageToken"] = next_page_token

            response = httpx.get(
                f"{settings.google_drive_api_base_url}/files",
                headers=headers,
                params=request_params,
                timeout=60.0,
            )
            response.raise_for_status()
            payload = response.json()

            for item in payload.get("files", []):
                item_id = str(item.get("id", "")).strip()
                item_name = str(item.get("name", "")).strip()
                if not item_id or not item_name:
                    continue

                folders.append(
                    ConnectorFolderOption(
                        id=item_id,
                        name=item_name,
                        path=f"/{item_name}",
                        provider=connector.provider,
                    )
                )

            next_page_token = str(payload.get("nextPageToken", "")).strip()
            if not next_page_token or len(folders) >= self.local_sync.BROWSE_FOLDER_LIMIT:
                break

        return ConnectorBrowseResponse(
            provider=connector.provider,
            folders=sorted(
                folders,
                key=lambda item: (item.path != "/", item.path.lower()),
            ),
        )

    def _get_drive_access_token(
        self,
        *,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> str:
        response = httpx.post(
            settings.google_drive_token_url,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("access_token", "")).strip()

    def _list_drive_files(
        self,
        *,
        access_token: str,
        folder_id: str,
        drive_id: str,
    ) -> list[dict[str, str]]:
        headers = {"Authorization": f"Bearer {access_token}"}
        root_folder_id = folder_id or "root"
        pending_folders: list[tuple[str, str]] = [(root_folder_id, "")]
        files: list[dict[str, str]] = []
        while pending_folders:
            current_folder_id, current_prefix = pending_folders.pop(0)
            next_page_token = ""

            while True:
                request_params: dict[str, str] = {
                    "q": f"trashed = false and '{current_folder_id}' in parents",
                    "fields": (
                        "nextPageToken,"
                        "files(id,name,mimeType,modifiedTime,webViewLink,driveId)"
                    ),
                    "pageSize": "200",
                    "includeItemsFromAllDrives": "true",
                    "supportsAllDrives": "true",
                }
                if drive_id:
                    request_params["corpora"] = "drive"
                    request_params["driveId"] = drive_id
                if next_page_token:
                    request_params["pageToken"] = next_page_token

                response = httpx.get(
                    f"{settings.google_drive_api_base_url}/files",
                    headers=headers,
                    params=request_params,
                    timeout=60.0,
                )
                response.raise_for_status()
                payload = response.json()

                for item in payload.get("files", []):
                    item_name = str(item.get("name", "")).strip()
                    mime_type = str(item.get("mimeType", "")).strip()
                    if not item_name or not mime_type:
                        continue

                    relative_prefix = (
                        f"{current_prefix}/{item_name}" if current_prefix else item_name
                    )
                    if mime_type == "application/vnd.google-apps.folder":
                        item_id = str(item.get("id", "")).strip()
                        if item_id:
                            pending_folders.append((item_id, relative_prefix))
                        continue

                    prepared = self._prepare_remote_file(
                        item,
                        relative_path=relative_prefix,
                    )
                    if prepared is None:
                        continue
                    files.append(prepared)

                next_page_token = str(payload.get("nextPageToken", "")).strip()
                if not next_page_token:
                    break

        return files

    def _prepare_remote_file(
        self,
        item: dict[str, object],
        *,
        relative_path: str,
    ) -> dict[str, str] | None:
        file_id = str(item.get("id", "")).strip()
        file_name = str(item.get("name", "")).strip()
        mime_type = str(item.get("mimeType", "")).strip()
        if not file_id or not file_name or not mime_type:
            return None

        if mime_type in self.GOOGLE_NATIVE_EXPORTS:
            export_mime_type, extension = self.GOOGLE_NATIVE_EXPORTS[mime_type]
            local_name = file_name if file_name.lower().endswith(extension) else f"{file_name}{extension}"
            source_uri = self._google_workspace_uri(file_id=file_id, mime_type=mime_type)
            download_url = (
                f"{settings.google_drive_api_base_url}/files/{file_id}/export?"
                f"{urlencode({'mimeType': export_mime_type})}"
            )
            return {
                "id": file_id,
                "name": file_name,
                "local_name": local_name,
                "relative_path": relative_path,
                "content_type": export_mime_type,
                "download_url": download_url,
                "source_uri": source_uri,
                "last_modified_at": str(item.get("modifiedTime", "")).strip()
                or datetime.now(UTC).isoformat(),
            }

        extension = Path(file_name).suffix.lower()
        if extension not in ConnectorSyncService.SUPPORTED_EXTENSIONS:
            return None

        source_uri = str(item.get("webViewLink", "")).strip() or f"gdrive://{file_id}"
        return {
            "id": file_id,
            "name": file_name,
            "local_name": file_name,
            "relative_path": relative_path,
            "content_type": mime_type,
            "download_url": f"{settings.google_drive_api_base_url}/files/{file_id}?alt=media",
            "source_uri": source_uri,
            "last_modified_at": str(item.get("modifiedTime", "")).strip()
            or datetime.now(UTC).isoformat(),
        }

    def _download_drive_file(
        self,
        *,
        remote_file: dict[str, str],
        access_token: str,
        target_path: Path,
    ) -> None:
        headers = {"Authorization": f"Bearer {access_token}"}
        with httpx.stream(
            "GET",
            remote_file["download_url"],
            headers=headers,
            timeout=120.0,
        ) as response:
            response.raise_for_status()
            with target_path.open("wb") as file_handle:
                for chunk in response.iter_bytes():
                    file_handle.write(chunk)

    def _google_workspace_uri(self, *, file_id: str, mime_type: str) -> str:
        if mime_type == "application/vnd.google-apps.document":
            return f"https://docs.google.com/document/d/{file_id}/edit"
        if mime_type == "application/vnd.google-apps.spreadsheet":
            return f"https://docs.google.com/spreadsheets/d/{file_id}/edit"
        if mime_type == "application/vnd.google-apps.presentation":
            return f"https://docs.google.com/presentation/d/{file_id}/edit"
        return f"https://drive.google.com/file/d/{file_id}/view"

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
