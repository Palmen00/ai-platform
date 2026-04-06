from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi import Query

from app.config import settings
from app.schemas.document import (
    DocumentBatchProcessResponse,
    DocumentListResponse,
    DocumentPreviewResponse,
    DocumentProcessResponse,
    DocumentSecurityResponse,
    DocumentSecurityUpdateRequest,
    DocumentUploadResponse,
)
from app.services.auth import auth_service, get_admin_token, require_admin_from_either_header
from app.services.documents import DocumentService
from app.services.logging_service import log_event
from app.services.ollama import OllamaService
from app.services.vector_store import VectorStoreService

router = APIRouter(prefix="/documents", tags=["documents"])
document_service = DocumentService()
ollama_service = OllamaService()
vector_store_service = VectorStoreService()


@router.get("", response_model=DocumentListResponse)
def list_documents(
    limit: int = Query(default=settings.document_list_limit_default, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    query: str = Query(default=""),
    status_filter: str = Query(default="all"),
    type_filter: str = Query(default="all"),
    source_filter: str = Query(default="all"),
    sort_order: str = Query(default="newest"),
    admin_token: str | None = Depends(get_admin_token),
) -> DocumentListResponse:
    is_admin = auth_service.has_admin_access(admin_token)
    (
        documents,
        total_count,
        available_types,
        available_sources,
        available_type_facets,
        available_source_facets,
    ) = (
        document_service.list_documents_for_ui(
        limit=limit,
        offset=offset,
        query=query,
        status_filter=status_filter,
        type_filter=type_filter,
        source_filter=source_filter,
        sort_order=sort_order,
        is_admin=is_admin,
        )
    )
    return DocumentListResponse(
        documents=documents,
        total_count=total_count,
        offset=offset,
        limit=limit,
        has_more=(offset + len(documents)) < total_count,
        available_types=available_types,
        available_sources=available_sources,
        available_type_facets=available_type_facets,
        available_source_facets=available_source_facets,
    )


@router.get("/{document_id}/preview", response_model=DocumentPreviewResponse)
def get_document_preview(
    document_id: str,
    chunk: int | None = Query(default=None, ge=0),
    admin_token: str | None = Depends(get_admin_token),
) -> DocumentPreviewResponse:
    try:
        preview = document_service.get_document_preview(
            document_id,
            focus_chunk_index=chunk,
            is_admin=auth_service.has_admin_access(admin_token),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return DocumentPreviewResponse(preview=preview)


@router.post("/upload", response_model=DocumentUploadResponse)
def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> DocumentUploadResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="A file is required.")

    try:
        document = document_service.save_upload(file)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    document = document_service.queue_document_processing(document.id)
    background_tasks.add_task(document_service.process_document, document.id)
    log_event(
        "document.upload",
        "Document uploaded and queued for processing.",
        document_id=document.id,
        document_name=document.original_name,
        processing_status=document.processing_status,
        processing_stage=document.processing_stage,
        indexing_status=document.indexing_status or "pending",
    )
    return DocumentUploadResponse(document=document)


@router.post("/{document_id}/process", response_model=DocumentProcessResponse)
def process_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    admin_token: str | None = Depends(get_admin_token),
) -> DocumentProcessResponse:
    try:
        if document_service.get_document_for_viewer(
            document_id,
            is_admin=auth_service.has_admin_access(admin_token),
        ) is None:
            raise FileNotFoundError(f"Document {document_id} not found")
        document = document_service.queue_document_processing(document_id)
        background_tasks.add_task(document_service.process_document, document_id)
    except FileNotFoundError as exc:
        log_event(
            "document.process",
            "Document process failed because the document was not found.",
            status="error",
            document_id=document_id,
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    log_event(
        "document.process",
        "Document queued for processing.",
        document_id=document.id,
        document_name=document.original_name,
        processing_status=document.processing_status,
        processing_stage=document.processing_stage,
        indexing_status=document.indexing_status or "pending",
    )
    return DocumentProcessResponse(document=document)


@router.post("/reprocess-all", response_model=DocumentBatchProcessResponse)
def reprocess_all_documents(
    background_tasks: BackgroundTasks,
) -> DocumentBatchProcessResponse:
    documents = document_service.queue_all_documents_processing()
    for document in documents:
        background_tasks.add_task(document_service.process_document, document.id)

    log_event(
        "document.reprocess_all",
        "All documents queued for reprocessing.",
        queued_count=len(documents),
        document_ids=[document.id for document in documents],
    )
    return DocumentBatchProcessResponse(
        documents=documents,
        retried_count=0,
        queued_count=len(documents),
    )


@router.post("/retry-indexing", response_model=DocumentBatchProcessResponse)
def retry_incomplete_documents() -> DocumentBatchProcessResponse:
    documents = document_service.retry_incomplete_documents()
    log_event(
        "document.retry_indexing",
        "Retried incomplete document indexing.",
        retried_count=len(documents),
        document_ids=[document.id for document in documents],
    )
    return DocumentBatchProcessResponse(
        documents=documents,
        retried_count=len(documents),
    )


@router.post("/recover", response_model=DocumentBatchProcessResponse)
def recover_incomplete_documents() -> DocumentBatchProcessResponse:
    ollama_status = ollama_service.get_status()
    qdrant_status = vector_store_service.get_status()

    if ollama_status.status != "ok" or qdrant_status.status != "ok":
        log_event(
            "document.recover",
            "Automatic recovery skipped because runtime dependencies are not healthy.",
            status="warning",
            ollama_status=ollama_status.status,
            qdrant_status=qdrant_status.status,
        )
        raise HTTPException(
            status_code=409,
            detail="Runtime dependencies are not healthy enough for recovery.",
        )

    documents = document_service.retry_incomplete_documents()
    log_event(
        "document.recover",
        "Automatic recovery completed for retriable documents.",
        retried_count=len(documents),
        document_ids=[document.id for document in documents],
    )
    return DocumentBatchProcessResponse(
        documents=documents,
        retried_count=len(documents),
    )


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    admin_token: str | None = Depends(get_admin_token),
) -> dict[str, str]:
    if document_service.get_document_for_viewer(
        document_id,
        is_admin=auth_service.has_admin_access(admin_token),
    ) is None:
        log_event(
            "document.delete",
            "Document delete failed because the document was not found.",
            status="error",
            document_id=document_id,
        )
        raise HTTPException(status_code=404, detail="Document not found.")

    deleted = document_service.delete_document(document_id)
    if not deleted:
        log_event(
            "document.delete",
            "Document delete failed because the document was not found.",
            status="error",
            document_id=document_id,
        )
        raise HTTPException(status_code=404, detail="Document not found.")

    log_event("document.delete", "Document deleted.", document_id=document_id)
    return {"status": "deleted", "id": document_id}


@router.put(
    "/{document_id}/security",
    response_model=DocumentSecurityResponse,
    dependencies=[Depends(require_admin_from_either_header)],
)
def update_document_security(
    document_id: str,
    payload: DocumentSecurityUpdateRequest,
) -> DocumentSecurityResponse:
    try:
        document = document_service.update_document_visibility(
            document_id,
            visibility=payload.visibility,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    log_event(
        "document.security",
        "Document visibility updated.",
        document_id=document.id,
        document_name=document.original_name,
        visibility=document.visibility,
    )
    return DocumentSecurityResponse(document=document)
