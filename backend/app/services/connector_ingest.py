from pathlib import Path

from app.schemas.connector import ConnectorImportRequest
from app.schemas.connector import ConnectorImportResult
from app.services.documents import DocumentService


class ConnectorIngestService:
    """Generic entrypoint for future external source connectors.

    This keeps SharePoint, Google Workspace, OneDrive, or local-folder sync
    lanes focused on fetch/export, while the main document pipeline continues
    to own storage, processing, indexing, and retrieval.
    """

    def __init__(self) -> None:
        self.document_service = DocumentService()

    def import_file(self, request: ConnectorImportRequest) -> ConnectorImportResult:
        source_path = Path(request.file_path)
        if not source_path.exists() or not source_path.is_file():
            raise FileNotFoundError(f"Connector import source not found: {source_path}")

        document = self.document_service.import_external_document(
            file_path=source_path,
            original_name=request.original_name,
            content_type=request.content_type,
            source_connector_id=request.connector_id,
            source_provider=request.provider,
            source_uri=request.source_uri,
            source_container=request.container,
            source_last_modified_at=request.source_last_modified_at,
            visibility=request.visibility,
            access_usernames=request.access_usernames,
        )
        return ConnectorImportResult(
            document_id=document.id,
            original_name=document.original_name,
            source_origin=document.source_origin,
            source_provider=document.source_provider,
            source_uri=document.source_uri,
            source_container=document.source_container,
        )
