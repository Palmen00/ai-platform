from pydantic import BaseModel, Field


class DocumentSignal(BaseModel):
    value: str
    normalized: str
    category: str
    score: float
    source: str | None = None


class DocumentRecord(BaseModel):
    id: str
    original_name: str
    stored_name: str
    content_type: str
    size_bytes: int
    uploaded_at: str
    source_origin: str = "upload"
    source_connector_id: str | None = None
    source_provider: str | None = None
    source_uri: str | None = None
    source_container: str | None = None
    source_last_modified_at: str | None = None
    document_title: str | None = None
    source_kind: str | None = None
    visibility: str = "standard"
    access_usernames: list[str] = Field(default_factory=list)
    section_count: int = 0
    detected_document_type: str | None = None
    document_entities: list[str] = Field(default_factory=list)
    document_signals: list[DocumentSignal] = Field(default_factory=list)
    document_date: str | None = None
    document_date_label: str | None = None
    document_date_kind: str | None = None
    processing_status: str = "pending"
    processing_stage: str = "queued"
    processing_started_at: str | None = None
    processing_updated_at: str | None = None
    ocr_used: bool = False
    ocr_status: str = "not_needed"
    ocr_engine: str | None = None
    ocr_error: str | None = None
    character_count: int = 0
    chunk_count: int = 0
    last_processed_at: str | None = None
    processing_error: str | None = None
    indexing_status: str = "pending"
    indexed_at: str | None = None
    indexing_error: str | None = None


class DocumentFacetOption(BaseModel):
    value: str
    count: int


class DocumentListResponse(BaseModel):
    documents: list[DocumentRecord]
    total_count: int
    offset: int = 0
    limit: int
    has_more: bool = False
    available_types: list[str] = Field(default_factory=list)
    available_sources: list[str] = Field(default_factory=list)
    available_type_facets: list[DocumentFacetOption] = Field(default_factory=list)
    available_source_facets: list[DocumentFacetOption] = Field(default_factory=list)


class DocumentUploadResponse(BaseModel):
    document: DocumentRecord


class DocumentSecurityUpdateRequest(BaseModel):
    visibility: str
    access_usernames: list[str] = Field(default_factory=list)


class DocumentSecurityResponse(BaseModel):
    document: DocumentRecord


class DocumentProcessResponse(BaseModel):
    document: DocumentRecord


class DocumentBatchProcessResponse(BaseModel):
    documents: list[DocumentRecord]
    retried_count: int
    queued_count: int | None = None


class DocumentPreviewChunk(BaseModel):
    index: int
    content: str
    section_title: str | None = None
    page_number: int | None = None


class DocumentPreview(BaseModel):
    document: DocumentRecord
    extracted_text: str
    extracted_text_truncated: bool = False
    chunks: list[DocumentPreviewChunk]
    focused_chunk_index: int | None = None


class DocumentPreviewResponse(BaseModel):
    preview: DocumentPreview
