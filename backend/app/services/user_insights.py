from __future__ import annotations

from pathlib import Path

from app.schemas.user import LocalUserRecord, LocalUserSummary, UserWorkspaceStats
from app.services.conversations import ConversationService
from app.services.documents import DocumentService
from app.services.users import UserService


class UserInsightsService:
    def __init__(self) -> None:
        self.user_service = UserService()
        self.conversation_service = ConversationService()
        self.document_service = DocumentService()

    def list_user_summaries_with_stats(self) -> list[LocalUserSummary]:
        users = self.user_service.list_users()
        documents = self.document_service.list_documents()
        return [
            LocalUserSummary.model_validate(
                {
                    **self.user_service.to_summary(user).model_dump(),
                    "stats": self._build_stats_for_user(user, documents=documents).model_dump(),
                }
            )
            for user in users
        ]

    def _build_stats_for_user(
        self,
        user: LocalUserRecord,
        *,
        documents,
    ) -> UserWorkspaceStats:
        owned_conversations = self.conversation_service.list_conversations(
            owner_username=user.username,
            is_admin=False,
        )
        visible_documents = self.document_service._filter_documents_for_viewer(  # noqa: SLF001
            documents,
            is_admin=user.role == "admin",
            viewer_username=user.username,
        )

        conversation_storage_bytes = sum(
            self._conversation_storage_bytes(conversation.id)
            for conversation in owned_conversations
        )
        accessible_document_storage_bytes = sum(
            document.size_bytes for document in visible_documents
        )

        return UserWorkspaceStats(
            conversation_count=len(owned_conversations),
            message_count=sum(
                conversation.message_count for conversation in owned_conversations
            ),
            conversation_storage_bytes=conversation_storage_bytes,
            accessible_document_count=len(visible_documents),
            accessible_document_storage_bytes=accessible_document_storage_bytes,
        )

    def _conversation_storage_bytes(self, conversation_id: str) -> int:
        path = self.conversation_service._conversation_path(conversation_id)  # noqa: SLF001
        if not Path(path).exists():
            return 0
        try:
            return path.stat().st_size
        except OSError:
            return 0
