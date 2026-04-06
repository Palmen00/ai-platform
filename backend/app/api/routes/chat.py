from fastapi import APIRouter, Depends, HTTPException

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.auth import auth_service, get_admin_token
from app.services.chat_orchestrator import ChatOrchestrator
from app.services.logging_service import log_event

router = APIRouter()
chat_orchestrator = ChatOrchestrator()


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    admin_token: str | None = Depends(get_admin_token),
) -> ChatResponse:
    try:
        response = chat_orchestrator.respond(
            payload,
            is_admin=auth_service.has_admin_access(admin_token),
        )
        log_event(
            "chat.reply",
            "Chat response generated.",
            conversation_id=response.conversation_id or "",
            model=response.model or "",
            source_count=len(response.sources),
            retrieval_mode=response.retrieval.mode if response.retrieval else "none",
            message_length=len(payload.message.strip()),
        )
        return response
    except Exception as exc:
        log_event(
            "chat.reply",
            "Chat response failed.",
            status="error",
            model=payload.model or "",
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach Ollama or generate a response: {exc}",
        ) from exc
