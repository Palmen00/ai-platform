from app.schemas.connector import ConnectorBrowseResponse
from app.schemas.connector import ConnectorManifest
from app.schemas.connector import ConnectorSyncResponse
from app.services.connector_sync import ConnectorSyncService
from app.services.google_drive_connector import GoogleDriveConnectorService
from app.services.sharepoint_connector import SharePointConnectorService


class ConnectorDispatcherService:
    """Provider dispatcher for connector sync operations."""

    def __init__(self) -> None:
        self.sharepoint = SharePointConnectorService()
        self.google_drive = GoogleDriveConnectorService()
        self.local_sync = ConnectorSyncService()

    def sync(
        self,
        connector: ConnectorManifest,
        *,
        dry_run: bool = False,
    ) -> ConnectorSyncResponse:
        provider = (connector.provider or "").strip().lower()

        if self.sharepoint.supports(connector):
            return self.sharepoint.sync(connector, dry_run=dry_run)

        if self.google_drive.supports(connector):
            return self.google_drive.sync(connector, dry_run=dry_run)

        if provider in {"local", "filesystem", "folder"}:
            return self.local_sync.sync_local_connector(connector, dry_run=dry_run)

        raise NotImplementedError(
            f"No sync provider is implemented yet for '{connector.provider}'."
        )

    def browse(self, connector: ConnectorManifest) -> ConnectorBrowseResponse:
        provider = (connector.provider or "").strip().lower()

        if self.google_drive.supports(connector):
            return self.google_drive.browse(connector)

        if provider in {"local", "filesystem", "folder"}:
            return self.local_sync.browse_local_connector(connector)

        raise NotImplementedError(
            f"No browse provider is implemented yet for '{connector.provider}'."
        )
