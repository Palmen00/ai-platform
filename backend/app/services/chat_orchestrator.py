from app.config import settings
from app.schemas.chat import ChatHistoryMessage, ChatRequest, ChatResponse
from app.services.generation import GenerationService
from app.services.conversations import ConversationService
from app.services.retrieval import RetrievalService


class ChatOrchestrator:
    def __init__(self) -> None:
        self.retrieval_service = RetrievalService()
        self.generation_service = GenerationService()
        self.conversation_service = ConversationService()

    @property
    def default_model(self) -> str:
        return self.generation_service.default_model

    def respond(self, payload: ChatRequest, *, is_admin: bool = False) -> ChatResponse:
        user_message = payload.message.strip()
        if not user_message:
            return ChatResponse(reply="Please enter a message.", model=payload.model)

        selected_model = payload.model or self.default_model
        retrieval_result = self.retrieval_service.retrieve(
            user_message,
            limit=settings.retrieval_limit,
            allowed_document_ids=payload.document_ids,
            is_admin=is_admin,
        )
        sources = retrieval_result.sources
        direct_reply = self.retrieval_service.build_grounded_document_reply(
            user_message,
            sources,
            allowed_document_ids=payload.document_ids,
            history=payload.history,
            is_admin=is_admin,
        )
        if direct_reply and (
            self.retrieval_service.document_service.is_document_inventory_query(
                user_message
            )
            or self.retrieval_service.document_service.is_document_similarity_query(
                user_message
            )
            or self.retrieval_service.document_service.is_document_metadata_inventory_query(
                user_message
            )
        ):
            sources = []
            retrieval_result.sources = []
            retrieval_result.debug.returned_sources = 0
            retrieval_result.debug.mode = "none"
        retrieval_result.debug.grounded_reply_used = direct_reply is not None
        if direct_reply:
            reply = direct_reply
        elif sources and retrieval_result.debug.document_reference:
            retrieval_result.debug.grounded_reply_used = True
            reply = self.generation_service.generate_grounded_document_reply(
                model=selected_model,
                history=payload.history,
                user_message=user_message,
                sources=sources,
            )
        else:
            reply = self.generation_service.generate_chat_reply(
                model=selected_model,
                history=payload.history,
                user_message=user_message,
                sources=sources,
            )

        conversation_id: str | None = payload.conversation_id

        if payload.persist_conversation:
            conversation = self.conversation_service.append_round_trip(
                conversation_id=payload.conversation_id,
                user_message=ChatHistoryMessage(
                    role="user",
                    content=user_message,
                ),
                assistant_message=ChatHistoryMessage(
                    role="assistant",
                    content=reply,
                    model=selected_model,
                    sources=sources,
                    retrieval=retrieval_result.debug,
                ),
                model=selected_model,
                document_ids=payload.document_ids,
            )
            conversation_id = conversation.id

        return ChatResponse(
            reply=reply,
            model=selected_model,
            sources=sources,
            retrieval=retrieval_result.debug,
            conversation_id=conversation_id,
        )
