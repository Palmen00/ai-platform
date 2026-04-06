from pydantic import BaseModel, Field


class ConnectorImportRequest(BaseModel):
    file_path: str
    original_name: str | None = None
    content_type: str = "application/octet-stream"
    provider: str | None = None
    source_uri: str | None = None
    container: str | None = None
    source_last_modified_at: str | None = None


class ConnectorImportResult(BaseModel):
    document_id: str
    original_name: str
    source_origin: str
    source_provider: str | None = None
    source_uri: str | None = None
    source_container: str | None = None
    action: str = "imported"


class ConnectorManifest(BaseModel):
    id: str
    name: str
    provider: str
    enabled: bool = True
    auth_mode: str = "manual"
    root_path: str | None = None
    container: str | None = None
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    export_formats: list[str] = Field(default_factory=list)
    provider_settings: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None
    last_sync_at: str | None = None
    created_at: str
    updated_at: str


class ConnectorCreateRequest(BaseModel):
    name: str
    provider: str
    enabled: bool = True
    auth_mode: str = "manual"
    root_path: str | None = None
    container: str | None = None
    include_patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    export_formats: list[str] = Field(default_factory=list)
    provider_settings: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None


class ConnectorUpdateRequest(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    auth_mode: str | None = None
    root_path: str | None = None
    container: str | None = None
    include_patterns: list[str] | None = None
    exclude_patterns: list[str] | None = None
    export_formats: list[str] | None = None
    provider_settings: dict[str, str] | None = None
    notes: str | None = None
    last_sync_at: str | None = None


class ConnectorBrowseRequest(BaseModel):
    provider: str
    auth_mode: str = "manual"
    root_path: str | None = None
    provider_settings: dict[str, str] = Field(default_factory=dict)


class ConnectorFolderOption(BaseModel):
    id: str
    name: str
    path: str
    provider: str


class ConnectorBrowseResponse(BaseModel):
    provider: str
    folders: list[ConnectorFolderOption] = Field(default_factory=list)


class ConnectorListResponse(BaseModel):
    connectors: list[ConnectorManifest] = Field(default_factory=list)


class ConnectorResponse(BaseModel):
    connector: ConnectorManifest


class ConnectorSyncResult(BaseModel):
    document_id: str | None = None
    original_name: str
    source_uri: str | None = None
    action: str


class ConnectorSyncResponse(BaseModel):
    connector_id: str
    dry_run: bool = False
    scanned_count: int
    imported_count: int
    updated_count: int
    skipped_count: int
    results: list[ConnectorSyncResult] = Field(default_factory=list)
