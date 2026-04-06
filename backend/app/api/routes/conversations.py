from fastapi import APIRouter, Depends, HTTPException

from app.schemas.chat import (
    ConversationCreateRequest,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdateRequest,
)
from app.services.auth import require_authenticated_session
from app.services.conversations import ConversationService
from app.services.logging_service import log_event

router = APIRouter(prefix="/conversations", tags=["conversations"])
conversation_service = ConversationService()


@router.get("", response_model=ConversationListResponse)
def list_conversations(session=Depends(require_authenticated_session)) -> ConversationListResponse:
    conversations = conversation_service.list_conversations(
        owner_username=session.username if session else None,
        is_admin=bool(session and session.is_admin),
    )
    return ConversationListResponse(conversations=conversations)


@router.post("", response_model=ConversationResponse)
def create_conversation(
    payload: ConversationCreateRequest | None = None,
    session=Depends(require_authenticated_session),
) -> ConversationResponse:
    conversation = conversation_service.create_conversation(
        payload,
        owner_username=session.username if session else None,
    )
    log_event(
        "conversation.create",
        "Conversation created.",
        conversation_id=conversation.id,
        model=conversation.model or "",
    )
    return ConversationResponse(conversation=conversation)


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: str,
    session=Depends(require_authenticated_session),
) -> ConversationResponse:
    conversation = conversation_service.get_conversation(
        conversation_id,
        owner_username=session.username if session else None,
        is_admin=bool(session and session.is_admin),
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    return ConversationResponse(conversation=conversation)


@router.put("/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdateRequest,
    session=Depends(require_authenticated_session),
) -> ConversationResponse:
    conversation = conversation_service.update_conversation(
        conversation_id,
        payload,
        owner_username=session.username if session else None,
        is_admin=bool(session and session.is_admin),
    )
    if conversation is None:
        log_event(
            "conversation.update",
            "Conversation update failed because the conversation was not found.",
            status="error",
            conversation_id=conversation_id,
        )
        raise HTTPException(status_code=404, detail="Conversation not found.")

    log_event(
        "conversation.update",
        "Conversation updated.",
        conversation_id=conversation.id,
        message_count=conversation.message_count,
    )
    return ConversationResponse(conversation=conversation)


@router.delete("/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    session=Depends(require_authenticated_session),
) -> dict[str, str]:
    deleted = conversation_service.delete_conversation(
        conversation_id,
        owner_username=session.username if session else None,
        is_admin=bool(session and session.is_admin),
    )
    if not deleted:
        log_event(
            "conversation.delete",
            "Conversation delete failed because the conversation was not found.",
            status="error",
            conversation_id=conversation_id,
        )
        raise HTTPException(status_code=404, detail="Conversation not found.")

    log_event(
        "conversation.delete",
        "Conversation deleted.",
        conversation_id=conversation_id,
    )
    return {"status": "deleted", "id": conversation_id}
