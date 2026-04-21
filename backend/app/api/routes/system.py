from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.schemas.settings import (
    BackupExportPayload,
    BackupImportResponse,
    CleanupRequest,
    CleanupResponse,
    RecoveryStatus,
    RuntimeSettings,
    RuntimeSettingsResponse,
    StorageStatus,
    StorageUsageItem,
    SystemStatusResponse,
)
from app.services.conversations import ConversationService
from app.services.documents import DocumentService
from app.services.auth import (
    ensure_safe_mode_allows,
    get_actor_log_fields,
    require_admin_from_either_header,
)
from app.services.logging_service import log_event
from app.services.maintenance import maintenance_service
from app.services.ollama import OllamaService
from app.services.vector_store import VectorStoreService

router = APIRouter()
ollama_service = OllamaService()
document_service = DocumentService()
conversation_service = ConversationService()
vector_store_service = VectorStoreService()


def _directory_size(path: Path, recursive: bool = True) -> int:
    if not path.exists():
        return 0

    if path.is_file():
        return path.stat().st_size

    if recursive:
        return sum(
            child.stat().st_size
            for child in path.rglob("*")
            if child.is_file()
        )

    return sum(
        child.stat().st_size
        for child in path.glob("*")
        if child.is_file()
    )


def _build_storage_usage_items() -> list[StorageUsageItem]:
    entries = [
        StorageUsageItem(
            key="uploads",
            label="Uploads",
            path=str(settings.uploads_dir),
            size_bytes=_directory_size(settings.uploads_dir),
            cleanable=False,
            description="Original uploaded files.",
        ),
        StorageUsageItem(
            key="qdrant",
            label="Qdrant storage",
            path=str(settings.qdrant_storage_dir),
            size_bytes=_directory_size(settings.qdrant_storage_dir),
            cleanable=False,
            description="Persistent vector index data.",
        ),
        StorageUsageItem(
            key="conversations",
            label="Saved chats",
            path=str(settings.conversations_dir),
            size_bytes=_directory_size(settings.conversations_dir),
            cleanable=False,
            description="Stored conversation history.",
        ),
        StorageUsageItem(
            key="document_metadata",
            label="Document metadata",
            path=str(settings.documents_metadata_dir),
            size_bytes=_directory_size(settings.documents_metadata_dir, recursive=False),
            cleanable=False,
            description="Document records and runtime metadata.",
        ),
        StorageUsageItem(
            key="document_chunks",
            label="Document chunks",
            path=str(settings.document_chunks_dir),
            size_bytes=_directory_size(settings.document_chunks_dir),
            cleanable=False,
            description="Chunked text used for retrieval.",
        ),
        StorageUsageItem(
            key="extracted_text",
            label="Extracted text",
            path=str(settings.document_extracted_text_dir),
            size_bytes=_directory_size(settings.document_extracted_text_dir),
            cleanable=False,
            description="Parsed text generated from uploaded files.",
        ),
        StorageUsageItem(
            key="cache",
            label="App cache",
            path=str(settings.app_cache_dir),
            size_bytes=_directory_size(settings.app_cache_dir),
            cleanable=True,
            description="Safe-to-regenerate application cache.",
        ),
        StorageUsageItem(
            key="logs",
            label="Logs",
            path=str(settings.logs_dir),
            size_bytes=_directory_size(settings.logs_dir),
            cleanable=True,
            description="Runtime logs and event files.",
        ),
    ]

    return entries


@router.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "running",
        "environment": settings.app_env,
        "ollama_base_url": settings.ollama_base_url,
    }


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


@router.get("/status", response_model=SystemStatusResponse)
def system_status() -> SystemStatusResponse:
    documents = document_service.list_documents()
    conversations = conversation_service.list_conversations()
    ollama_status = ollama_service.get_status()
    qdrant_status = vector_store_service.get_status()
    maintenance_status = maintenance_service.get_idle_status()
    document_intelligence = document_service.get_document_intelligence_status(
        maintenance_status=maintenance_status,
        is_admin=True,
    )
    usage_items = _build_storage_usage_items()
    dependencies_ready = (
        ollama_status.status == "ok" and qdrant_status.status == "ok"
    )
    retriable_documents = document_service.count_retriable_documents()

    overall_status = "ok"
    if not dependencies_ready:
        overall_status = "degraded"

    return SystemStatusResponse(
        status=overall_status,
        environment=settings.app_env,
        app_name=settings.app_name,
        ollama=ollama_status,
        qdrant=qdrant_status,
        storage=StorageStatus(
            documents_total=len(documents),
            processed_documents=sum(
                1 for document in documents if document.processing_status == "processed"
            ),
            indexed_documents=sum(
                1 for document in documents if document.indexing_status == "indexed"
            ),
            failed_documents=sum(
                1
                for document in documents
                if document.processing_status == "failed"
                or document.indexing_status == "failed"
            ),
            conversations_total=len(conversations),
            total_size_bytes=sum(item.size_bytes for item in usage_items),
            usage_items=usage_items,
        ),
        recovery=RecoveryStatus(
            dependencies_ready=dependencies_ready,
            retriable_documents=retriable_documents,
            auto_retry_recommended=dependencies_ready and retriable_documents > 0,
        ),
        document_intelligence=document_intelligence.summary,
        maintenance=maintenance_status,
    )


@router.get("/models")
def models() -> dict[str, list[dict[str, object]]]:
    try:
        models_payload = ollama_service.list_models()
        log_event(
            "system.models",
            "Fetched models from Ollama.",
            model_count=len(models_payload),
        )
        return {"models": models_payload}
    except Exception as exc:
        log_event(
            "system.models",
            "Model fetch failed.",
            status="error",
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch models from Ollama: {exc}",
        ) from exc


@router.get("/settings", response_model=RuntimeSettingsResponse)
def get_runtime_settings(
    _: None = Depends(require_admin_from_either_header),
) -> RuntimeSettingsResponse:
    return RuntimeSettingsResponse(
        settings=RuntimeSettings.model_validate(
            settings.get_runtime_settings_payload()
        )
    )


@router.put("/settings", response_model=RuntimeSettingsResponse)
def update_runtime_settings(
    payload: RuntimeSettings,
    session=Depends(require_admin_from_either_header),
) -> RuntimeSettingsResponse:
    ensure_safe_mode_allows("Runtime setting changes")
    if payload.document_chunk_overlap >= payload.document_chunk_size:
        raise HTTPException(
            status_code=422,
            detail="Chunk overlap must be smaller than chunk size.",
        )

    updated_settings = settings.update_runtime_settings(payload.model_dump())
    log_event(
        "settings.update",
        "Runtime settings updated.",
        category="audit",
        **get_actor_log_fields(session),
        **updated_settings,
    )
    return RuntimeSettingsResponse(
        settings=RuntimeSettings.model_validate(updated_settings)
    )


@router.post("/cleanup", response_model=CleanupResponse)
def cleanup_storage(
    payload: CleanupRequest,
    session=Depends(require_admin_from_either_header),
) -> CleanupResponse:
    ensure_safe_mode_allows("Storage cleanup")
    if not payload.targets:
        raise HTTPException(status_code=422, detail="At least one cleanup target is required.")

    try:
        cleaned_targets = maintenance_service.cleanup_targets(payload.targets)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log_event(
            "system.cleanup",
            "Cleanup failed.",
            status="error",
            category="audit",
            **get_actor_log_fields(session),
            targets=payload.targets,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Cleanup failed.") from exc

    removed_bytes = sum(item.removed_bytes for item in cleaned_targets)
    log_event(
        "system.cleanup",
        "Cleanup completed.",
        category="audit",
        **get_actor_log_fields(session),
        targets=[item.key for item in cleaned_targets],
        removed_bytes=removed_bytes,
    )
    return CleanupResponse(
        cleaned_targets=cleaned_targets,
        removed_bytes=removed_bytes,
        message="Cleanup completed.",
    )


@router.get("/export", response_model=BackupExportPayload)
def export_backup(
    session=Depends(require_admin_from_either_header),
) -> BackupExportPayload:
    ensure_safe_mode_allows("Backup export")
    documents = [document.model_dump() for document in document_service.list_documents()]
    conversations = [
        conversation.model_dump()
        for conversation in conversation_service.list_conversations()
    ]
    log_event(
        "system.export",
        "Backup export generated.",
        category="audit",
        **get_actor_log_fields(session),
        document_count=len(documents),
        conversation_count=len(conversations),
    )
    return BackupExportPayload(
        generated_at=datetime.now(UTC).isoformat(),
        app_name=settings.app_name,
        environment=settings.app_env,
        runtime_settings=settings.get_runtime_settings_payload(),
        documents=documents,
        conversations=conversations,
    )


@router.post("/import", response_model=BackupImportResponse)
def import_backup(
    payload: BackupExportPayload,
    session=Depends(require_admin_from_either_header),
) -> BackupImportResponse:
    ensure_safe_mode_allows("Backup import")
    imported_runtime_settings = False

    if payload.runtime_settings:
        runtime_settings = RuntimeSettings.model_validate(payload.runtime_settings)
        settings.update_runtime_settings(runtime_settings.model_dump())
        imported_runtime_settings = True

    imported_conversations = conversation_service.import_conversations(
        payload.conversations
    )
    skipped_documents = len(payload.documents)

    log_event(
        "system.import",
        "Backup import completed.",
        category="audit",
        **get_actor_log_fields(session),
        imported_conversations=imported_conversations,
        imported_runtime_settings=imported_runtime_settings,
        skipped_documents=skipped_documents,
    )

    message = (
        "Backup imported. Runtime settings and conversations were restored. "
        "Document files and vector data were not restored in this step."
    )
    return BackupImportResponse(
        imported_conversations=imported_conversations,
        imported_runtime_settings=imported_runtime_settings,
        skipped_documents=skipped_documents,
        message=message,
    )
