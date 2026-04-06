import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.config import settings
from app.schemas.chat import (
    ChatHistoryMessage,
    ConversationCreateRequest,
    ConversationDetail,
    ConversationUpdateRequest,
)


class ConversationService:
    def __init__(self) -> None:
        self.conversations_dir = settings.conversations_dir

    def list_conversations(
        self,
        owner_username: str | None = None,
        *,
        is_admin: bool = False,
    ) -> list[ConversationDetail]:
        conversations: list[ConversationDetail] = []

        for path in sorted(self.conversations_dir.glob("*.json")):
            with path.open("r", encoding="utf-8") as file_handle:
                payload = json.load(file_handle)
                conversation = ConversationDetail.model_validate(payload)
                if not self._conversation_visible_to_user(
                    conversation,
                    owner_username=owner_username,
                    is_admin=is_admin,
                ):
                    continue
                conversations.append(conversation)

        return sorted(conversations, key=lambda item: item.updated_at, reverse=True)

    def create_conversation(
        self,
        payload: ConversationCreateRequest | None = None,
        *,
        owner_username: str | None = None,
    ) -> ConversationDetail:
        now = datetime.now(UTC).isoformat()
        conversation = ConversationDetail(
            id=uuid4().hex,
            title=(payload.title if payload and payload.title else "New chat"),
            model=payload.model if payload else None,
            document_ids=payload.document_ids if payload else [],
            message_count=0,
            owner_username=owner_username,
            created_at=now,
            updated_at=now,
            messages=[],
        )
        self._write_conversation(conversation)
        return conversation

    def get_conversation(
        self,
        conversation_id: str,
        *,
        owner_username: str | None = None,
        is_admin: bool = False,
    ) -> ConversationDetail | None:
        path = self._conversation_path(conversation_id)
        if not path.exists():
            return None

        with path.open("r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)

        conversation = ConversationDetail.model_validate(payload)
        if not self._conversation_visible_to_user(
            conversation,
            owner_username=owner_username,
            is_admin=is_admin,
        ):
            return None
        return conversation

    def update_conversation(
        self,
        conversation_id: str,
        payload: ConversationUpdateRequest,
        *,
        owner_username: str | None = None,
        is_admin: bool = False,
    ) -> ConversationDetail | None:
        conversation = self.get_conversation(
            conversation_id,
            owner_username=owner_username,
            is_admin=is_admin,
        )
        if conversation is None:
            return None

        if payload.title is not None:
            conversation.title = payload.title

        if payload.model is not None:
            conversation.model = payload.model

        if payload.document_ids is not None:
            conversation.document_ids = payload.document_ids

        if payload.messages is not None:
            conversation.messages = payload.messages
            conversation.message_count = len(payload.messages)

        conversation.updated_at = datetime.now(UTC).isoformat()

        if (
            conversation.title == "New chat"
            and payload.messages
            and payload.messages[0].role == "user"
        ):
            conversation.title = self._derive_title(payload.messages[0].content)

        self._write_conversation(conversation)
        return conversation

    def delete_conversation(
        self,
        conversation_id: str,
        *,
        owner_username: str | None = None,
        is_admin: bool = False,
    ) -> bool:
        conversation = self.get_conversation(
            conversation_id,
            owner_username=owner_username,
            is_admin=is_admin,
        )
        if conversation is None:
            return False

        self._conversation_path(conversation_id).unlink()
        return True

    def append_round_trip(
        self,
        conversation_id: str | None,
        user_message: ChatHistoryMessage,
        assistant_message: ChatHistoryMessage,
        model: str | None,
        document_ids: list[str] | None = None,
        *,
        owner_username: str | None = None,
        is_admin: bool = False,
    ) -> ConversationDetail:
        conversation = (
            self.get_conversation(
                conversation_id,
                owner_username=owner_username,
                is_admin=is_admin,
            )
            if conversation_id
            else None
        )
        if conversation is None:
            conversation = self.create_conversation(
                ConversationCreateRequest(model=model, document_ids=document_ids or []),
                owner_username=owner_username,
            )

        conversation.model = model
        conversation.document_ids = document_ids or []
        if conversation.owner_username is None and owner_username:
            conversation.owner_username = owner_username
        conversation.messages.extend([user_message, assistant_message])
        conversation.message_count = len(conversation.messages)
        conversation.updated_at = datetime.now(UTC).isoformat()

        if conversation.title == "New chat":
            conversation.title = self._derive_title(user_message.content)

        self._write_conversation(conversation)
        return conversation

    def import_conversations(self, payloads: list[dict[str, object]]) -> int:
        imported_count = 0

        for payload in payloads:
            conversation = ConversationDetail.model_validate(payload)
            self._write_conversation(conversation)
            imported_count += 1

        return imported_count

    def _conversation_path(self, conversation_id: str) -> Path:
        return self.conversations_dir / f"{conversation_id}.json"

    def _write_conversation(self, conversation: ConversationDetail) -> None:
        path = self._conversation_path(conversation.id)
        with path.open("w", encoding="utf-8") as file_handle:
            json.dump(
                conversation.model_dump(),
                file_handle,
                ensure_ascii=True,
                indent=2,
            )

    def _derive_title(self, content: str) -> str:
        normalized = " ".join(content.split()).strip()
        if not normalized:
            return "New chat"

        return normalized[:60] + ("..." if len(normalized) > 60 else "")

    def _conversation_visible_to_user(
        self,
        conversation: ConversationDetail,
        *,
        owner_username: str | None,
        is_admin: bool,
    ) -> bool:
        if is_admin:
            return True

        if not owner_username:
            return conversation.owner_username is None

        return conversation.owner_username == owner_username
