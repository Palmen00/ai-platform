from pydantic import BaseModel, Field


class RuntimeSettings(BaseModel):
    ollama_base_url: str
    ollama_default_model: str
    ollama_embed_model: str
    qdrant_url: str
    retrieval_limit: int = Field(ge=1, le=20)
    retrieval_min_score: float = Field(ge=0.0, le=1.0)
    document_chunk_size: int = Field(ge=200, le=4000)
    document_chunk_overlap: int = Field(ge=0, le=1000)


class RuntimeSettingsResponse(BaseModel):
    settings: RuntimeSettings


class CleanupRequest(BaseModel):
    targets: list[str] = Field(default_factory=list)


class CleanupTargetResult(BaseModel):
    key: str
    label: str
    removed_bytes: int


class CleanupResponse(BaseModel):
    cleaned_targets: list[CleanupTargetResult] = Field(default_factory=list)
    removed_bytes: int = 0
    message: str = ""


class RecoveryStatus(BaseModel):
    dependencies_ready: bool = False
    retriable_documents: int = 0
    auto_retry_recommended: bool = False


class BackupExportPayload(BaseModel):
    generated_at: str
    app_name: str
    environment: str
    runtime_settings: dict[str, object]
    documents: list[dict[str, object]]
    conversations: list[dict[str, object]]


class BackupImportResponse(BaseModel):
    imported_conversations: int
    imported_runtime_settings: bool = False
    skipped_documents: int = 0
    message: str = ""


class DependencyStatus(BaseModel):
    status: str
    url: str
    detail: str = ""
    model_count: int | None = None
    collection_name: str | None = None
    collection_exists: bool | None = None
    indexed_point_count: int | None = None


class StorageStatus(BaseModel):
    documents_total: int
    processed_documents: int
    indexed_documents: int
    failed_documents: int
    conversations_total: int
    total_size_bytes: int = 0
    usage_items: list["StorageUsageItem"] = Field(default_factory=list)


class StorageUsageItem(BaseModel):
    key: str
    label: str
    path: str
    size_bytes: int
    cleanable: bool = False
    description: str = ""


class SystemStatusResponse(BaseModel):
    status: str
    environment: str
    app_name: str
    ollama: DependencyStatus
    qdrant: DependencyStatus
    storage: StorageStatus
    recovery: RecoveryStatus
