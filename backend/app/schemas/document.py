from pydantic import BaseModel, Field


class DocumentSignal(BaseModel):
    value: str
    normalized: str
    category: str
    score: float
    source: str | None = None


class DocumentCommercialLineItem(BaseModel):
    description: str
    quantity: float | None = None
    unit_price: float | None = None
    total: float | None = None
    currency: str | None = None
    sku: str | None = None
    source_line: str | None = None
    confidence: float = 0.0


class DocumentCommercialSummary(BaseModel):
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    subtotal: float | None = None
    tax: float | None = None
    total: float | None = None
    currency: str | None = None
    line_items: list[DocumentCommercialLineItem] = Field(default_factory=list)


class DocumentSimilarityMatch(BaseModel):
    document_id: str
    document_name: str
    score: float
    shared_terms: list[str] = Field(default_factory=list)
    reason: str | None = None


class DocumentFamilyMember(BaseModel):
    document_id: str
    document_name: str
    document_date: str | None = None
    version_label: str | None = None
    uploaded_at: str | None = None


class DocumentFamilySummary(BaseModel):
    family_key: str
    family_label: str
    document_count: int
    latest_document_id: str
    latest_document_name: str
    latest_document_date: str | None = None
    topics: list[str] = Field(default_factory=list)
    members: list[DocumentFamilyMember] = Field(default_factory=list)


class DocumentIntelligenceSummary(BaseModel):
    total_documents: int = 0
    processed_documents: int = 0
    profile_ready_documents: int = 0
    family_ready_documents: int = 0
    versioned_documents: int = 0
    topic_ready_documents: int = 0
    total_families: int = 0
    stale_documents: int = 0


class DocumentMaintenanceStatus(BaseModel):
    enabled: bool = False
    poll_seconds: int = 0
    user_idle_seconds: int = 0
    batch_size: int = 0
    last_run_at: str | None = None
    pending_documents: int = 0
    seconds_since_user_activity: float = 0.0
    active_jobs: dict[str, int] = Field(default_factory=dict)


class DocumentIntelligenceResponse(BaseModel):
    summary: DocumentIntelligenceSummary
    maintenance: DocumentMaintenanceStatus
    families: list[DocumentFamilySummary] = Field(default_factory=list)
    stale_documents: list[DocumentFamilyMember] = Field(default_factory=list)


class DocumentIntelligenceRefreshResponse(BaseModel):
    refreshed_document_ids: list[str] = Field(default_factory=list)
    refreshed_count: int = 0
    status: DocumentIntelligenceResponse


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
    document_family_key: str | None = None
    document_family_label: str | None = None
    document_version_label: str | None = None
    document_version_number: int | None = None
    document_topics: list[str] = Field(default_factory=list)
    document_summary_anchor: str | None = None
    commercial_summary: DocumentCommercialSummary | None = None
    similarity_profile: str | None = None
    similarity_terms: list[str] = Field(default_factory=list)
    similar_documents: list[DocumentSimilarityMatch] = Field(default_factory=list)
    similarity_updated_at: str | None = None
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
