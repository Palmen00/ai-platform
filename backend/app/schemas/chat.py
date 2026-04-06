from typing import Literal

from pydantic import BaseModel, Field


class ChatHistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = ""
    model: str | None = None
    sources: list["ChatSource"] = Field(default_factory=list)
    retrieval: "RetrievalDebug | None" = None


class ChatRequest(BaseModel):
    message: str
    model: str | None = None
    history: list[ChatHistoryMessage] = Field(default_factory=list)
    conversation_id: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    persist_conversation: bool = True


class ChatSource(BaseModel):
    document_id: str
    document_name: str
    chunk_index: int
    score: float
    excerpt: str
    section_title: str | None = None
    page_number: int | None = None
    source_kind: str | None = None
    detected_document_type: str | None = None
    document_date: str | None = None
    document_date_label: str | None = None
    ocr_used: bool = False


class RetrievalDebug(BaseModel):
    mode: Literal["none", "hybrid", "semantic", "term"]
    query_terms: list[str] = Field(default_factory=list)
    semantic_candidates: int = 0
    term_candidates: int = 0
    returned_sources: int = 0
    top_source_score: float = 0.0
    confidence: Literal["low", "medium", "high"] = "low"
    document_reference: bool = False
    grounded_reply_used: bool = False
    document_filter_active: bool = False
    document_filter_count: int = 0
    metadata_filter_active: bool = False
    metadata_filter_count: int = 0
    requested_document_type: str | None = None
    requested_document_year: int | None = None


class ChatResponse(BaseModel):
    reply: str
    model: str | None = None
    sources: list[ChatSource] = Field(default_factory=list)
    retrieval: RetrievalDebug | None = None
    conversation_id: str | None = None


class ConversationSummary(BaseModel):
    id: str
    title: str
    model: str | None = None
    document_ids: list[str] = Field(default_factory=list)
    message_count: int = 0
    owner_username: str | None = None
    created_at: str
    updated_at: str


class ConversationDetail(ConversationSummary):
    messages: list[ChatHistoryMessage] = Field(default_factory=list)


class ConversationCreateRequest(BaseModel):
    title: str | None = None
    model: str | None = None
    document_ids: list[str] = Field(default_factory=list)


class ConversationUpdateRequest(BaseModel):
    title: str | None = None
    model: str | None = None
    document_ids: list[str] | None = None
    messages: list[ChatHistoryMessage] | None = None


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]


class ConversationResponse(BaseModel):
    conversation: ConversationDetail
