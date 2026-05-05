import { API_BASE_URL } from "./config";

function withAdminHeaders(
  init?: RequestInit & { timeoutMs?: number }
): RequestInit & { timeoutMs?: number } {
  return {
    ...(init ?? {}),
    credentials: "include",
  };
}

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init?: RequestInit & { timeoutMs?: number }
) {
  const { timeoutMs = 15000, ...requestInit } = withAdminHeaders(init);
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(input, {
      ...requestInit,
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export type HealthResponse = {
  status: string;
};

export type AuthStatusResponse = {
  auth_enabled: boolean;
  auth_configured: boolean;
  authenticated: boolean;
  safe_mode_enabled: boolean;
  username?: string | null;
  role?: "admin" | "viewer" | null;
  session_expires_at?: string | null;
};

export type LoginResponse = {
  expires_at: string;
  remember_me?: boolean;
  auth_enabled: boolean;
  auth_configured: boolean;
  authenticated: boolean;
  safe_mode_enabled: boolean;
  username: string;
  role: "admin" | "viewer";
};

export type ModelItem = {
  id: string;
  name: string;
  size: string;
  provider: string;
  installed: boolean;
  capability?: string;
};

export type ModelsResponse = {
  models: ModelItem[];
  error?: string;
};

export type ChatHistoryItem = {
  role: "user" | "assistant";
  content: string;
  model?: string;
  sources?: ChatSource[];
  retrieval?: RetrievalDebug | null;
};

export type ChatResponse = {
  reply: string;
  model?: string;
  sources?: ChatSource[];
  retrieval?: RetrievalDebug | null;
  conversation_id?: string;
};

export type ChatSource = {
  document_id: string;
  document_name: string;
  chunk_index: number;
  score: number;
  excerpt: string;
  section_title?: string | null;
  page_number?: number | null;
  source_kind?: string | null;
  detected_document_type?: string | null;
  document_date?: string | null;
  document_date_label?: string | null;
  ocr_used?: boolean;
  ocr_engine?: string | null;
};

export type DocumentSignal = {
  value: string;
  normalized: string;
  category: string;
  score: number;
  source?: string | null;
};

export type DocumentSimilarityMatch = {
  document_id: string;
  document_name: string;
  score: number;
  shared_terms: string[];
  reason?: string | null;
};

export type DocumentFamilyMember = {
  document_id: string;
  document_name: string;
  document_date?: string | null;
  version_label?: string | null;
  uploaded_at?: string | null;
};

export type DocumentFamilySummary = {
  family_key: string;
  family_label: string;
  document_count: number;
  latest_document_id: string;
  latest_document_name: string;
  latest_document_date?: string | null;
  topics: string[];
  members: DocumentFamilyMember[];
};

export type DocumentIntelligenceSummary = {
  total_documents: number;
  processed_documents: number;
  profile_ready_documents: number;
  family_ready_documents: number;
  versioned_documents: number;
  topic_ready_documents: number;
  total_families: number;
  stale_documents: number;
};

export type DocumentMaintenanceStatus = {
  enabled: boolean;
  poll_seconds: number;
  user_idle_seconds: number;
  batch_size: number;
  last_run_at?: string | null;
  pending_documents: number;
  seconds_since_user_activity: number;
  active_jobs: Record<string, number>;
};

export type DocumentIntelligenceResponse = {
  summary: DocumentIntelligenceSummary;
  maintenance: DocumentMaintenanceStatus;
  families: DocumentFamilySummary[];
  stale_documents: DocumentFamilyMember[];
};

export type DocumentIntelligenceRefreshResponse = {
  refreshed_document_ids: string[];
  refreshed_count: number;
  status: DocumentIntelligenceResponse;
};

export type RetrievalDebug = {
  mode: "none" | "hybrid" | "semantic" | "term";
  query_terms: string[];
  semantic_candidates: number;
  term_candidates: number;
  returned_sources: number;
  top_source_score: number;
  confidence: "low" | "medium" | "high";
  document_reference: boolean;
  grounded_reply_used: boolean;
  document_filter_active: boolean;
  document_filter_count: number;
  metadata_filter_active: boolean;
  metadata_filter_count: number;
  requested_document_type?: string | null;
  requested_document_year?: number | null;
};

export type ConversationSummary = {
  id: string;
  title: string;
  model?: string | null;
  document_ids: string[];
  message_count: number;
  owner_username?: string | null;
  created_at: string;
  updated_at: string;
};

export type ConversationDetail = ConversationSummary & {
  messages: ChatHistoryItem[];
};

export type ConversationsResponse = {
  conversations: ConversationSummary[];
};

export type ConversationResponse = {
  conversation: ConversationDetail;
};

export type DocumentCommercialLineItem = {
  description: string;
  quantity?: number | null;
  unit_price?: number | null;
  total?: number | null;
  currency?: string | null;
  sku?: string | null;
  source_line?: string | null;
  confidence: number;
};

export type DocumentCommercialSummary = {
  invoice_number?: string | null;
  invoice_date?: string | null;
  due_date?: string | null;
  subtotal?: number | null;
  tax?: number | null;
  total?: number | null;
  currency?: string | null;
  line_items: DocumentCommercialLineItem[];
};

export type DocumentItem = {
  id: string;
  original_name: string;
  stored_name: string;
  content_type: string;
  size_bytes: number;
  content_sha256?: string | null;
  uploaded_at: string;
  source_origin: string;
  source_provider?: string | null;
  source_uri?: string | null;
  source_container?: string | null;
  source_last_modified_at?: string | null;
  document_title?: string | null;
  source_kind?: string | null;
  visibility?: string;
  access_usernames?: string[];
  section_count?: number;
  detected_document_type?: string | null;
  document_entities?: string[];
  document_signals?: DocumentSignal[];
  document_date?: string | null;
  document_date_label?: string | null;
  document_date_kind?: string | null;
  document_family_key?: string | null;
  document_family_label?: string | null;
  document_version_label?: string | null;
  document_version_number?: number | null;
  document_topics?: string[];
  document_summary_anchor?: string | null;
  commercial_summary?: DocumentCommercialSummary | null;
  similarity_profile?: string | null;
  similarity_terms?: string[];
  similar_documents?: DocumentSimilarityMatch[];
  similarity_updated_at?: string | null;
  processing_status: string;
  processing_stage: string;
  processing_started_at?: string | null;
  processing_updated_at?: string | null;
  ocr_used: boolean;
  ocr_status: string;
  ocr_engine?: string | null;
  ocr_error?: string | null;
  character_count: number;
  chunk_count: number;
  last_processed_at?: string | null;
  processing_error?: string | null;
  indexing_status?: string;
  indexed_at?: string | null;
  indexing_error?: string | null;
};

export type DocumentFacetOption = {
  value: string;
  count: number;
};

export type DocumentsResponse = {
  documents: DocumentItem[];
  total_count: number;
  offset: number;
  limit: number;
  has_more: boolean;
  available_types: string[];
  available_sources: string[];
  available_type_facets: DocumentFacetOption[];
  available_source_facets: DocumentFacetOption[];
};

export type DocumentDuplicateMatch = {
  document_id: string;
  document_name: string;
  match_type: string;
  confidence: string;
  reason?: string | null;
};

export type DocumentUploadWarning = {
  type: string;
  message: string;
  matches: DocumentDuplicateMatch[];
};

export type DocumentUploadResult = {
  document: DocumentItem;
  warnings: DocumentUploadWarning[];
};

export type ConnectorManifest = {
  id: string;
  name: string;
  provider: string;
  enabled: boolean;
  auth_mode: string;
  root_path?: string | null;
  container?: string | null;
  document_visibility: "standard" | "hidden" | "restricted";
  access_usernames: string[];
  include_patterns: string[];
  exclude_patterns: string[];
  export_formats: string[];
  provider_settings: Record<string, string>;
  notes?: string | null;
  last_sync_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type ConnectorsResponse = {
  connectors: ConnectorManifest[];
};

export type ConnectorCreateInput = {
  name: string;
  provider: string;
  enabled?: boolean;
  auth_mode?: string;
  root_path?: string | null;
  container?: string | null;
  document_visibility?: "standard" | "hidden" | "restricted";
  access_usernames?: string[];
  include_patterns?: string[];
  exclude_patterns?: string[];
  export_formats?: string[];
  provider_settings?: Record<string, string>;
  notes?: string | null;
};

export type ConnectorUpdateInput = {
  name?: string;
  enabled?: boolean;
  auth_mode?: string;
  root_path?: string | null;
  container?: string | null;
  document_visibility?: "standard" | "hidden" | "restricted";
  access_usernames?: string[];
  include_patterns?: string[];
  exclude_patterns?: string[];
  export_formats?: string[];
  provider_settings?: Record<string, string>;
  notes?: string | null;
  last_sync_at?: string | null;
};

export type ConnectorResponse = {
  connector: ConnectorManifest;
};

export type ConnectorBrowseInput = {
  provider: string;
  auth_mode?: string;
  root_path?: string | null;
  provider_settings?: Record<string, string>;
};

export type ConnectorFolderOption = {
  id: string;
  name: string;
  path: string;
  provider: string;
};

export type ConnectorBrowseResponse = {
  provider: string;
  folders: ConnectorFolderOption[];
};

export type ConnectorSyncResult = {
  document_id?: string | null;
  original_name: string;
  source_uri?: string | null;
  action: string;
};

export type ConnectorSyncResponse = {
  connector_id: string;
  dry_run: boolean;
  scanned_count: number;
  imported_count: number;
  updated_count: number;
  skipped_count: number;
  results: ConnectorSyncResult[];
};

export type LocalUserSummary = {
  id: string;
  username: string;
  role: "admin" | "viewer";
  enabled: boolean;
  created_at: string;
  updated_at: string;
  last_login_at?: string | null;
  failed_login_attempts?: number;
  locked_until?: string | null;
  stats: {
    conversation_count: number;
    message_count: number;
    conversation_storage_bytes: number;
    accessible_document_count: number;
    accessible_document_storage_bytes: number;
  };
};

export type UsersResponse = {
  users: LocalUserSummary[];
};

export type UserResponse = {
  user: LocalUserSummary;
};

export type CreateUserInput = {
  username: string;
  password: string;
  role?: "admin" | "viewer";
  enabled?: boolean;
};

export type UpdateUserInput = {
  username?: string;
  password?: string;
  role?: "admin" | "viewer";
  enabled?: boolean;
};

export type DocumentBatchProcessResponse = {
  documents: DocumentItem[];
  retried_count: number;
  queued_count?: number | null;
};

export type DocumentPreviewChunk = {
  index: number;
  content: string;
  section_title?: string | null;
  page_number?: number | null;
};

export type DocumentPreview = {
  document: DocumentItem;
  extracted_text: string;
  extracted_text_truncated: boolean;
  chunks: DocumentPreviewChunk[];
  focused_chunk_index?: number | null;
};

export type DocumentPreviewResponse = {
  preview: DocumentPreview;
};

export type DocumentSecurityResponse = {
  document: DocumentItem;
};

export type DocumentSecurityUpdateInput = {
  visibility: "standard" | "hidden" | "restricted";
  accessUsernames?: string[];
};

export type RuntimeSettings = {
  ollama_base_url: string;
  ollama_default_model: string;
  ollama_embed_model: string;
  qdrant_url: string;
  retrieval_limit: number;
  retrieval_min_score: number;
  document_chunk_size: number;
  document_chunk_overlap: number;
};

export type RuntimeSettingsResponse = {
  settings: RuntimeSettings;
};

export type CleanupTargetResult = {
  key: string;
  label: string;
  removed_bytes: number;
};

export type CleanupResponse = {
  cleaned_targets: CleanupTargetResult[];
  removed_bytes: number;
  message: string;
};

export type BackupExportPayload = {
  generated_at: string;
  app_name: string;
  environment: string;
  runtime_settings: Record<string, unknown>;
  documents: Record<string, unknown>[];
  conversations: Record<string, unknown>[];
};

export type BackupImportResponse = {
  imported_conversations: number;
  imported_runtime_settings: boolean;
  skipped_documents: number;
  message: string;
};

export type DependencyStatus = {
  status: string;
  url: string;
  detail: string;
  model_count?: number | null;
  collection_name?: string | null;
  collection_exists?: boolean | null;
  indexed_point_count?: number | null;
};

export type StorageStatus = {
  documents_total: number;
  processed_documents: number;
  indexed_documents: number;
  failed_documents: number;
  conversations_total: number;
  total_size_bytes: number;
  usage_items: StorageUsageItem[];
};

export type StorageUsageItem = {
  key: string;
  label: string;
  path: string;
  size_bytes: number;
  cleanable: boolean;
  description: string;
};

export type RecoveryStatus = {
  dependencies_ready: boolean;
  retriable_documents: number;
  auto_retry_recommended: boolean;
};

export type SystemStatusResponse = {
  status: string;
  environment: string;
  app_name: string;
  ollama: DependencyStatus;
  qdrant: DependencyStatus;
  storage: StorageStatus;
  recovery: RecoveryStatus;
  document_intelligence: DocumentIntelligenceSummary;
  maintenance: DocumentMaintenanceStatus;
};

export type LogEvent = {
  timestamp: string;
  event_type: string;
  category: string;
  status: string;
  message: string;
  actor_user_id?: string | null;
  actor_username?: string | null;
  actor_role?: "admin" | "viewer" | null;
  details: Record<string, unknown>;
};

export type LogsResponse = {
  events: LogEvent[];
  raw_lines: string[];
};

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch health status");
  }

  return response.json();
}

export async function getAuthStatus(): Promise<AuthStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/status`, {
    ...withAdminHeaders({
      cache: "no-store",
    }),
  });

  if (!response.ok) {
    throw new Error("Failed to fetch auth status");
  }

  return response.json();
}

export async function loginUser(
  username: string,
  password: string,
  rememberMe = false
): Promise<AuthStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ username, password, remember_me: rememberMe }),
  });

  if (!response.ok) {
    let detail = "Failed to log in";
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        detail = payload.detail;
      }
    } catch {
      // Ignore JSON parsing issues and keep default error text.
    }
    throw new Error(detail);
  }

  const payload = (await response.json()) as LoginResponse;
  return {
    auth_enabled: payload.auth_enabled,
    auth_configured: payload.auth_configured,
    authenticated: payload.authenticated,
    safe_mode_enabled: payload.safe_mode_enabled,
    username: payload.username,
    role: payload.role,
    session_expires_at: payload.expires_at,
  };
}

export async function logoutAdmin(): Promise<void> {
  await fetch(`${API_BASE_URL}/auth/logout`, {
    method: "POST",
    credentials: "include",
  });
}

export async function getModels(): Promise<ModelsResponse> {
  const response = await fetch(`${API_BASE_URL}/models`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch models");
  }

  return response.json();
}

export async function sendChatMessage(
  message: string,
  model: string,
  history: ChatHistoryItem[],
  conversationId?: string,
  documentIds?: string[],
  persistConversation = true
): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE_URL}/chat`, withAdminHeaders({
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      message,
      model,
      history,
      conversation_id: conversationId ?? null,
      document_ids: documentIds ?? [],
      persist_conversation: persistConversation,
    }),
  }));

  if (!response.ok) {
    let errorMessage = "Failed to send chat message";
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        errorMessage = payload.detail;
      }
    } catch {
      // Keep the generic fallback when the backend does not return JSON.
    }
    throw new Error(errorMessage);
  }

  return response.json();
}

export async function getConversations(): Promise<ConversationsResponse> {
  const response = await fetch(`${API_BASE_URL}/conversations`, withAdminHeaders({
    cache: "no-store",
  }));

  if (!response.ok) {
    throw new Error("Failed to fetch conversations");
  }

  return response.json();
}

export async function createConversation(
  payload?: { title?: string; model?: string }
): Promise<ConversationDetail> {
  const response = await fetch(`${API_BASE_URL}/conversations`, withAdminHeaders({
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload ?? {}),
  }));

  if (!response.ok) {
    throw new Error("Failed to create conversation");
  }

  const data = (await response.json()) as ConversationResponse;
  return data.conversation;
}

export async function getConversation(
  conversationId: string
): Promise<ConversationDetail> {
  const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}`, withAdminHeaders({
    cache: "no-store",
  }));

  if (!response.ok) {
    throw new Error("Failed to fetch conversation");
  }

  const data = (await response.json()) as ConversationResponse;
  return data.conversation;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}`, withAdminHeaders({
    method: "DELETE",
  }));

  if (!response.ok) {
    throw new Error("Failed to delete conversation");
  }
}

export async function updateConversationTitle(
  conversationId: string,
  title: string
): Promise<ConversationDetail> {
  const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}`, withAdminHeaders({
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      title,
    }),
  }));

  if (!response.ok) {
    throw new Error("Failed to update conversation");
  }

  const data = (await response.json()) as ConversationResponse;
  return data.conversation;
}

export async function getDocuments(options?: {
  limit?: number;
  offset?: number;
  query?: string;
  statusFilter?: string;
  typeFilter?: string;
  sourceFilter?: string;
  sortOrder?: string;
}): Promise<DocumentsResponse> {
  const documentsUrl = new URL(`${API_BASE_URL}/documents`);
  if (options?.limit !== undefined) {
    documentsUrl.searchParams.set("limit", String(options.limit));
  }
  if (options?.offset !== undefined) {
    documentsUrl.searchParams.set("offset", String(options.offset));
  }
  if (options?.query) {
    documentsUrl.searchParams.set("query", options.query);
  }
  if (options?.statusFilter) {
    documentsUrl.searchParams.set("status_filter", options.statusFilter);
  }
  if (options?.typeFilter) {
    documentsUrl.searchParams.set("type_filter", options.typeFilter);
  }
  if (options?.sourceFilter) {
    documentsUrl.searchParams.set("source_filter", options.sourceFilter);
  }
  if (options?.sortOrder) {
    documentsUrl.searchParams.set("sort_order", options.sortOrder);
  }

  const response = await fetch(documentsUrl.toString(), {
    ...withAdminHeaders({
      cache: "no-store",
    }),
  });

  if (!response.ok) {
    throw new Error("Failed to fetch documents");
  }

  return response.json();
}

export async function getConnectors(): Promise<ConnectorsResponse> {
  const response = await fetchWithTimeout(`${API_BASE_URL}/connectors`, {
    cache: "no-store",
    timeoutMs: 8000,
  });

  if (!response.ok) {
    throw new Error("Failed to fetch connectors");
  }

  return response.json();
}

export async function getDocumentIntelligence(): Promise<DocumentIntelligenceResponse> {
  const response = await fetch(`${API_BASE_URL}/documents/intelligence`, withAdminHeaders({
    cache: "no-store",
  }));

  if (!response.ok) {
    throw new Error("Failed to fetch document intelligence");
  }

  return response.json();
}

export async function refreshDocumentIntelligence(): Promise<DocumentIntelligenceRefreshResponse> {
  const response = await fetch(
    `${API_BASE_URL}/documents/intelligence/refresh`,
    withAdminHeaders({
      method: "POST",
    })
  );

  if (!response.ok) {
    throw new Error("Failed to refresh document intelligence");
  }

  return response.json();
}

export async function getUsers(): Promise<UsersResponse> {
  const response = await fetch(`${API_BASE_URL}/auth/users`, withAdminHeaders({
    cache: "no-store",
  }));

  if (!response.ok) {
    throw new Error("Failed to fetch users");
  }

  return response.json();
}

export async function createUser(
  payload: CreateUserInput
): Promise<LocalUserSummary> {
  const response = await fetch(`${API_BASE_URL}/auth/users`, withAdminHeaders({
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }));

  if (!response.ok) {
    throw new Error("Failed to create user");
  }

  const data = (await response.json()) as UserResponse;
  return data.user;
}

export async function updateUser(
  userId: string,
  payload: UpdateUserInput
): Promise<LocalUserSummary> {
  const response = await fetch(`${API_BASE_URL}/auth/users/${userId}`, withAdminHeaders({
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }));

  if (!response.ok) {
    throw new Error("Failed to update user");
  }

  const data = (await response.json()) as UserResponse;
  return data.user;
}

export async function createConnector(
  payload: ConnectorCreateInput
): Promise<ConnectorManifest> {
  const response = await fetch(`${API_BASE_URL}/connectors`, withAdminHeaders({
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }));

  if (!response.ok) {
    let detail = "Failed to create connector";
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail || detail;
    } catch {
      // Keep fallback message if the backend did not return JSON.
    }
    throw new Error(detail);
  }

  const data = (await response.json()) as ConnectorResponse;
  return data.connector;
}

export async function browseConnector(
  payload: ConnectorBrowseInput
): Promise<ConnectorBrowseResponse> {
  const response = await fetch(`${API_BASE_URL}/connectors/browse`, withAdminHeaders({
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }));

  if (!response.ok) {
    throw new Error("Failed to browse connector folders");
  }

  return response.json();
}

export async function updateConnector(
  connectorId: string,
  payload: ConnectorUpdateInput
): Promise<ConnectorManifest> {
  const response = await fetch(`${API_BASE_URL}/connectors/${connectorId}`, withAdminHeaders({
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }));

  if (!response.ok) {
    let detail = "Failed to update connector";
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail || detail;
    } catch {
      // Keep fallback message if the backend did not return JSON.
    }
    throw new Error(detail);
  }

  const data = (await response.json()) as ConnectorResponse;
  return data.connector;
}

export async function deleteConnector(connectorId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/connectors/${connectorId}`, withAdminHeaders({
    method: "DELETE",
  }));

  if (!response.ok) {
    throw new Error("Failed to delete connector");
  }
}

export async function syncConnector(
  connectorId: string,
  options?: { dryRun?: boolean }
): Promise<ConnectorSyncResponse> {
  const syncUrl = new URL(`${API_BASE_URL}/connectors/${connectorId}/sync`);
  if (options?.dryRun) {
    syncUrl.searchParams.set("dry_run", "true");
  }

  const response = await fetch(syncUrl.toString(), withAdminHeaders({
    method: "POST",
  }));

  if (!response.ok) {
    throw new Error("Failed to sync connector");
  }

  return response.json();
}

export async function getRuntimeSettings(): Promise<RuntimeSettings> {
  const response = await fetch(`${API_BASE_URL}/settings`, withAdminHeaders({
    cache: "no-store",
  }));

  if (!response.ok) {
    throw new Error("Failed to fetch runtime settings");
  }

  const payload = (await response.json()) as RuntimeSettingsResponse;
  return payload.settings;
}

export async function getSystemStatus(): Promise<SystemStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/status`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch system status");
  }

  return response.json();
}

export async function updateRuntimeSettings(
  settings: RuntimeSettings
): Promise<RuntimeSettings> {
  const response = await fetch(`${API_BASE_URL}/settings`, withAdminHeaders({
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(settings),
  }));

  if (!response.ok) {
    throw new Error("Failed to update runtime settings");
  }

  const payload = (await response.json()) as RuntimeSettingsResponse;
  return payload.settings;
}

export async function cleanupStorageTargets(
  targets: string[]
): Promise<CleanupResponse> {
  const response = await fetch(`${API_BASE_URL}/cleanup`, withAdminHeaders({
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      targets,
    }),
  }));

  if (!response.ok) {
    throw new Error("Failed to run cleanup");
  }

  return response.json();
}

export async function getBackupExport(): Promise<BackupExportPayload> {
  const response = await fetch(`${API_BASE_URL}/export`, withAdminHeaders({
    cache: "no-store",
  }));

  if (!response.ok) {
    throw new Error("Failed to export backup");
  }

  return response.json();
}

export async function importBackup(
  payload: BackupExportPayload
): Promise<BackupImportResponse> {
  const response = await fetch(`${API_BASE_URL}/import`, withAdminHeaders({
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }));

  if (!response.ok) {
    throw new Error("Failed to import backup");
  }

  return response.json();
}

export async function getLogs(options?: {
  eventLimit?: number;
  lineLimit?: number;
  auditOnly?: boolean;
}): Promise<LogsResponse> {
  const eventLimit = options?.eventLimit ?? 50;
  const lineLimit = options?.lineLimit ?? 120;
  const auditOnly = options?.auditOnly ?? false;
  const logsUrl = new URL(`${API_BASE_URL}/logs`);
  logsUrl.searchParams.set("event_limit", String(eventLimit));
  logsUrl.searchParams.set("line_limit", String(lineLimit));
  if (auditOnly) {
    logsUrl.searchParams.set("audit_only", "true");
  }

  const response = await fetch(
    logsUrl.toString(),
    withAdminHeaders({
      cache: "no-store",
    })
  );

  if (!response.ok) {
    throw new Error("Failed to fetch logs");
  }

  return response.json();
}

export async function uploadDocumentWithWarnings(
  file: File
): Promise<DocumentUploadResult> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/documents/upload`, withAdminHeaders({
    method: "POST",
    body: formData,
  }));

  if (!response.ok) {
    let detail = "";
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail || "";
    } catch {
      // Fall back to a generic client-side error below.
    }
    throw new Error(detail || "Failed to upload document");
  }

  const payload = (await response.json()) as {
    document: DocumentItem;
    warnings?: DocumentUploadWarning[];
  };
  return {
    document: payload.document,
    warnings: payload.warnings ?? [],
  };
}

export async function uploadDocument(file: File): Promise<DocumentItem> {
  const payload = await uploadDocumentWithWarnings(file);
  return payload.document;
}

export async function deleteDocument(documentId: string): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/documents/${documentId}`,
    withAdminHeaders({
      method: "DELETE",
    })
  );

  if (!response.ok) {
    throw new Error("Failed to delete document");
  }
}

export async function processDocument(documentId: string): Promise<DocumentItem> {
  const response = await fetch(
    `${API_BASE_URL}/documents/${documentId}/process`,
    withAdminHeaders({
      method: "POST",
    })
  );

  if (!response.ok) {
    throw new Error("Failed to process document");
  }

  const payload = (await response.json()) as { document: DocumentItem };
  return payload.document;
}

export async function retryIncompleteDocuments(): Promise<DocumentBatchProcessResponse> {
  const response = await fetch(`${API_BASE_URL}/documents/retry-indexing`, withAdminHeaders({
    method: "POST",
  }));

  if (!response.ok) {
    throw new Error("Failed to retry incomplete documents");
  }

  return response.json();
}

export async function reprocessAllDocuments(): Promise<DocumentBatchProcessResponse> {
  const response = await fetch(`${API_BASE_URL}/documents/reprocess-all`, withAdminHeaders({
    method: "POST",
  }));

  if (!response.ok) {
    throw new Error("Failed to reprocess all documents");
  }

  return response.json();
}

export async function recoverIncompleteDocuments(): Promise<DocumentBatchProcessResponse> {
  const response = await fetch(`${API_BASE_URL}/documents/recover`, withAdminHeaders({
    method: "POST",
  }));

  if (!response.ok) {
    throw new Error("Failed to recover incomplete documents");
  }

  return response.json();
}

export async function getDocumentPreview(
  documentId: string,
  focusChunkIndex?: number
): Promise<DocumentPreview> {
  const previewUrl = new URL(`${API_BASE_URL}/documents/${documentId}/preview`);
  if (focusChunkIndex !== undefined) {
    previewUrl.searchParams.set("chunk", String(focusChunkIndex));
  }

  const response = await fetch(
    previewUrl.toString(),
    withAdminHeaders({
      cache: "no-store",
    })
  );

  if (!response.ok) {
    throw new Error("Failed to fetch document preview");
  }

  const payload = (await response.json()) as DocumentPreviewResponse;
  return payload.preview;
}

export async function updateDocumentSecurity(
  documentId: string,
  payload: DocumentSecurityUpdateInput
): Promise<DocumentItem> {
  const response = await fetch(
    `${API_BASE_URL}/documents/${documentId}/security`,
    withAdminHeaders({
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        visibility: payload.visibility,
        access_usernames: payload.accessUsernames ?? [],
      }),
    })
  );

  if (!response.ok) {
    let detail = "";
    try {
      const errorPayload = (await response.json()) as { detail?: string };
      detail = errorPayload.detail || "";
    } catch {
      // Keep generic fallback below.
    }
    throw new Error(detail || "Failed to update document visibility");
  }

  const responsePayload = (await response.json()) as DocumentSecurityResponse;
  return responsePayload.document;
}
