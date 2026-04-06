from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.connector import ConnectorBrowseRequest
from app.schemas.connector import ConnectorBrowseResponse
from app.schemas.connector import ConnectorCreateRequest
from app.schemas.connector import ConnectorImportRequest
from app.schemas.connector import ConnectorImportResult
from app.schemas.connector import ConnectorListResponse
from app.schemas.connector import ConnectorResponse
from app.schemas.connector import ConnectorSyncResponse
from app.schemas.connector import ConnectorUpdateRequest
from app.services.connector_dispatcher import ConnectorDispatcherService
from app.services.connector_ingest import ConnectorIngestService
from app.services.connector_registry import ConnectorRegistryService
from app.services.auth import ensure_safe_mode_allows, require_admin_from_either_header
from app.services.logging_service import log_event

router = APIRouter(
    prefix="/connectors",
    tags=["connectors"],
    dependencies=[Depends(require_admin_from_either_header)],
)
connector_registry = ConnectorRegistryService()
connector_ingest = ConnectorIngestService()
connector_dispatcher = ConnectorDispatcherService()


@router.get("", response_model=ConnectorListResponse)
def list_connectors() -> ConnectorListResponse:
    return ConnectorListResponse(connectors=connector_registry.list_connectors())


@router.post("/browse", response_model=ConnectorBrowseResponse)
def browse_connector(payload: ConnectorBrowseRequest) -> ConnectorBrowseResponse:
    connector = connector_registry.create_preview_connector(payload)

    try:
        result = connector_dispatcher.browse(connector)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    log_event(
        "connector.browse",
        "Connector folder browse completed.",
        provider=connector.provider,
        folder_count=len(result.folders),
    )
    return result


@router.post("", response_model=ConnectorResponse)
def create_connector(payload: ConnectorCreateRequest) -> ConnectorResponse:
    ensure_safe_mode_allows("Connector creation")
    connector = connector_registry.create_connector(payload)
    log_event(
        "connector.create",
        "Connector manifest created.",
        connector_id=connector.id,
        provider=connector.provider,
        enabled=connector.enabled,
    )
    return ConnectorResponse(connector=connector)


@router.get("/{connector_id}", response_model=ConnectorResponse)
def get_connector(connector_id: str) -> ConnectorResponse:
    connector = connector_registry.get_connector(connector_id)
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found.")
    return ConnectorResponse(connector=connector)


@router.put("/{connector_id}", response_model=ConnectorResponse)
def update_connector(
    connector_id: str,
    payload: ConnectorUpdateRequest,
) -> ConnectorResponse:
    ensure_safe_mode_allows("Connector updates")
    connector = connector_registry.update_connector(connector_id, payload)
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found.")

    log_event(
        "connector.update",
        "Connector manifest updated.",
        connector_id=connector.id,
        provider=connector.provider,
        enabled=connector.enabled,
    )
    return ConnectorResponse(connector=connector)


@router.delete("/{connector_id}")
def delete_connector(connector_id: str) -> dict[str, str]:
    ensure_safe_mode_allows("Connector deletion")
    deleted = connector_registry.delete_connector(connector_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Connector not found.")

    log_event(
        "connector.delete",
        "Connector manifest deleted.",
        connector_id=connector_id,
    )
    return {"status": "deleted", "id": connector_id}


@router.post("/{connector_id}/import-file", response_model=ConnectorImportResult)
def import_connector_file(
    connector_id: str,
    payload: ConnectorImportRequest,
) -> ConnectorImportResult:
    ensure_safe_mode_allows("Manual connector imports")
    connector = connector_registry.get_connector(connector_id)
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found.")

    if not connector.enabled:
        raise HTTPException(status_code=409, detail="Connector is disabled.")

    try:
        result = connector_ingest.import_file(
            payload.model_copy(
                update={
                    "provider": payload.provider or connector.provider,
                    "container": payload.container or connector.container,
                }
            )
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    log_event(
        "connector.import_file",
        "Connector file imported into the main document pipeline.",
        connector_id=connector.id,
        provider=result.source_provider or connector.provider,
        source_uri=result.source_uri or "",
        document_id=result.document_id,
    )
    return result


@router.post("/{connector_id}/sync", response_model=ConnectorSyncResponse)
def sync_connector(
    connector_id: str,
    dry_run: bool = Query(default=False),
) -> ConnectorSyncResponse:
    connector = connector_registry.get_connector(connector_id)
    if connector is None:
        raise HTTPException(status_code=404, detail="Connector not found.")

    if not connector.enabled:
        raise HTTPException(status_code=409, detail="Connector is disabled.")

    try:
        result = connector_dispatcher.sync(connector, dry_run=dry_run)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc

    if not dry_run:
        connector_registry.update_connector(
            connector.id,
            ConnectorUpdateRequest(last_sync_at=datetime.now(UTC).isoformat()),
        )

    log_event(
        "connector.sync.preview" if dry_run else "connector.sync",
        "Connector sync preview completed." if dry_run else "Connector sync completed.",
        connector_id=connector.id,
        provider=connector.provider,
        dry_run=dry_run,
        scanned_count=result.scanned_count,
        imported_count=result.imported_count,
        updated_count=result.updated_count,
        skipped_count=result.skipped_count,
    )
    return result


@router.post("/{connector_id}/sync-local", response_model=ConnectorSyncResponse)
def sync_local_connector(connector_id: str) -> ConnectorSyncResponse:
    return sync_connector(connector_id)
