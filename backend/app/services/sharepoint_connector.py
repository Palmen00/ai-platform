from __future__ import annotations

from datetime import UTC, datetime
from fnmatch import fnmatch
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx

from app.config import settings
from app.schemas.connector import ConnectorBrowseResponse
from app.schemas.connector import ConnectorFolderOption
from app.schemas.connector import ConnectorManifest
from app.schemas.connector import ConnectorSyncResponse
from app.schemas.connector import ConnectorSyncResult
from app.services.connector_sync import ConnectorSyncService
from app.services.documents import DocumentService


class SharePointConnectorService:
    """Provider-specific SharePoint connector.

    Current modes:
    - mock/manual/local: use local folder sync to simulate a SharePoint library
    - graph/client_credentials: use Microsoft Graph to list and download files
    """

    def __init__(self) -> None:
        self.local_sync = ConnectorSyncService()
        self.document_service = DocumentService()

    def supports(self, connector: ConnectorManifest) -> bool:
        return connector.provider.lower() == "sharepoint"

    def sync(
        self,
        connector: ConnectorManifest,
        *,
        dry_run: bool = False,
    ) -> ConnectorSyncResponse:
        auth_mode = (connector.auth_mode or "manual").strip().lower()
        if auth_mode in {"mock", "manual", "local"}:
            return self.local_sync.sync_local_connector(connector, dry_run=dry_run)
        if auth_mode in {"graph", "graph_client_credentials", "client_credentials"}:
            return self._sync_graph_connector(connector, dry_run=dry_run)

        raise ValueError(
            f"Unsupported SharePoint auth_mode '{connector.auth_mode}'."
        )

    def browse(self, connector: ConnectorManifest) -> ConnectorBrowseResponse:
        auth_mode = (connector.auth_mode or "manual").strip().lower()
        if auth_mode in {"mock", "manual", "local"} and connector.root_path:
            return self.local_sync.browse_local_connector(connector)
        if auth_mode in {"graph", "graph_client_credentials", "client_credentials"}:
            return self._browse_graph_connector(connector)

        raise ValueError(
            f"Unsupported SharePoint auth_mode '{connector.auth_mode}'."
        )

    def _sync_graph_connector(
        self,
        connector: ConnectorManifest,
        *,
        dry_run: bool = False,
    ) -> ConnectorSyncResponse:
        tenant_id = settings.sharepoint_tenant_id
        client_id = settings.sharepoint_client_id
        client_secret = settings.sharepoint_client_secret
        if not tenant_id or not client_id or not client_secret:
            raise ValueError(
                "SharePoint Graph sync requires SHAREPOINT_TENANT_ID, "
                "SHAREPOINT_CLIENT_ID, and SHAREPOINT_CLIENT_SECRET."
            )

        drive_id = connector.provider_settings.get("drive_id", "").strip()
        folder_path = connector.provider_settings.get("folder_path", "").strip().strip("/")
        if not drive_id:
            raise ValueError("SharePoint Graph sync requires provider_settings.drive_id.")

        access_token = self._get_graph_access_token(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )
        scanned_count = 0
        imported_count = 0
        updated_count = 0
        skipped_count = 0
        results: list[ConnectorSyncResult] = []
        max_files = self.local_sync._max_files_limit(connector)

        with TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            for remote_file in self._list_graph_files(
                access_token=access_token,
                drive_id=drive_id,
                folder_path=folder_path,
            ):
                relative_path = remote_file["relative_path"]
                if not self._matches_patterns(relative_path, connector.include_patterns, default=True):
                    continue
                if self._matches_patterns(relative_path, connector.exclude_patterns, default=False):
                    continue
                if Path(relative_path).suffix.lower() not in ConnectorSyncService.SUPPORTED_EXTENSIONS:
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
                    local_path = temp_root / Path(relative_path).name
                    self._download_graph_file(
                        download_url=remote_file["download_url"],
                        access_token=access_token,
                        target_path=local_path,
                    )
                    try:
                        document, action = self.document_service.upsert_external_document(
                            file_path=local_path,
                            original_name=remote_file["name"],
                            content_type=self.document_service._guess_content_type(local_path),
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
                        original_name=remote_file["name"],
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

    def _browse_graph_connector(
        self,
        connector: ConnectorManifest,
    ) -> ConnectorBrowseResponse:
        tenant_id = settings.sharepoint_tenant_id
        client_id = settings.sharepoint_client_id
        client_secret = settings.sharepoint_client_secret
        if not tenant_id or not client_id or not client_secret:
            raise ValueError(
                "SharePoint Graph browse requires SHAREPOINT_TENANT_ID, "
                "SHAREPOINT_CLIENT_ID, and SHAREPOINT_CLIENT_SECRET."
            )

        drive_id = connector.provider_settings.get("drive_id", "").strip()
        folder_path = connector.provider_settings.get("folder_path", "").strip().strip("/")
        folder_id = connector.provider_settings.get("folder_id", "").strip()
        if not drive_id:
            raise ValueError("SharePoint Graph browse requires provider_settings.drive_id.")

        access_token = self._get_graph_access_token(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )

        if folder_id:
            root_segment = f"items/{folder_id}"
        elif folder_path:
            root_segment = f"root:/{folder_path}:"
        else:
            root_segment = "root"

        response = httpx.get(
            f"{settings.sharepoint_graph_base_url}/drives/{drive_id}/{root_segment}/children",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=60.0,
        )
        response.raise_for_status()
        payload = response.json()

        folders = [
            ConnectorFolderOption(
                id=folder_id or "root",
                name=folder_path.split("/")[-1] if folder_path else "Root",
                path=folder_path,
                provider=connector.provider,
            )
        ]

        for item in payload.get("value", []):
            if "folder" not in item:
                continue
            item_id = str(item.get("id", "")).strip()
            item_name = str(item.get("name", "")).strip()
            if not item_id or not item_name:
                continue
            item_path = "/".join(part for part in (folder_path, item_name) if part)
            folders.append(
                ConnectorFolderOption(
                    id=item_id,
                    name=item_name,
                    path=item_path,
                    provider=connector.provider,
                )
            )

        return ConnectorBrowseResponse(
            provider=connector.provider,
            folders=folders,
        )

    def _get_graph_access_token(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
    ) -> str:
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        response = httpx.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://graph.microsoft.com/.default",
            },
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("access_token", "")).strip()

    def _list_graph_files(
        self,
        *,
        access_token: str,
        drive_id: str,
        folder_path: str,
    ) -> list[dict[str, str]]:
        root_segment = "root"
        if folder_path:
            root_segment = f"root:/{folder_path}:"

        pending_urls = [f"{settings.sharepoint_graph_base_url}/drives/{drive_id}/{root_segment}/children"]
        files: list[dict[str, str]] = []
        headers = {"Authorization": f"Bearer {access_token}"}

        while pending_urls:
            current_url = pending_urls.pop(0)
            response = httpx.get(current_url, headers=headers, timeout=60.0)
            response.raise_for_status()
            payload = response.json()

            for item in payload.get("value", []):
                item_name = str(item.get("name", "")).strip()
                if not item_name:
                    continue
                parent_path = str(item.get("parentReference", {}).get("path", "")).strip()
                relative_parent = parent_path.split("root:/", 1)[-1] if "root:/" in parent_path else ""
                relative_path = "/".join(part for part in (relative_parent, item_name) if part)

                if "folder" in item:
                    children_url = item.get("children@odata.navigationLink")
                    if not children_url:
                        item_id = item.get("id", "")
                        children_url = f"{settings.sharepoint_graph_base_url}/drives/{drive_id}/items/{item_id}/children"
                    pending_urls.append(str(children_url))
                    continue

                download_url = str(item.get("@microsoft.graph.downloadUrl", "")).strip()
                if not download_url:
                    item_id = str(item.get("id", "")).strip()
                    if item_id:
                        download_url = f"{settings.sharepoint_graph_base_url}/drives/{drive_id}/items/{item_id}/content"

                files.append(
                    {
                        "name": item_name,
                        "relative_path": relative_path or item_name,
                        "download_url": download_url,
                        "source_uri": str(item.get("webUrl", "")).strip() or f"sharepoint://{drive_id}/{relative_path or item_name}",
                        "last_modified_at": str(item.get("lastModifiedDateTime", "")).strip()
                        or datetime.now(UTC).isoformat(),
                    }
                )

            next_link = payload.get("@odata.nextLink")
            if next_link:
                pending_urls.append(str(next_link))

        return files

    def _download_graph_file(
        self,
        *,
        download_url: str,
        access_token: str,
        target_path: Path,
    ) -> None:
        headers = {}
        if download_url.startswith(settings.sharepoint_graph_base_url):
            headers["Authorization"] = f"Bearer {access_token}"

        with httpx.stream("GET", download_url, headers=headers, timeout=120.0) as response:
            response.raise_for_status()
            with target_path.open("wb") as file_handle:
                for chunk in response.iter_bytes():
                    file_handle.write(chunk)

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
