from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
import threading

from app.config import settings
from app.services.documents import DocumentService
from app.services.logging_service import log_event


class StarterKnowledgeService:
    def __init__(self) -> None:
        self.document_service = DocumentService()
        self.knowledge_dir = settings.backend_root / "app" / "starter_knowledge"
        self.install_dir = settings.app_data_root / "install"

    def ensure_seeded(self) -> None:
        if not settings.starter_knowledge_enabled:
            return

        documents_to_process: list[str] = []
        documents_to_process.extend(self._seed_static_documents())
        dynamic_document_id = self._seed_dynamic_server_profile()
        if dynamic_document_id:
            documents_to_process.append(dynamic_document_id)

        if documents_to_process:
            threading.Thread(
                target=self._process_documents_background,
                args=(documents_to_process,),
                daemon=True,
                name="starter-knowledge-indexer",
            ).start()

    def _seed_static_documents(self) -> list[str]:
        documents_to_process: list[str] = []
        for source_path in sorted(self.knowledge_dir.glob("*.md")):
            source_uri = f"starter://{source_path.stem}"
            document_id = self._upsert_document(
                source_path=source_path,
                original_name=source_path.name,
                source_uri=source_uri,
                source_container="starter_knowledge",
                source_last_modified_at=self._iso_timestamp_from_path(source_path),
            )
            if document_id:
                documents_to_process.append(document_id)

        return documents_to_process

    def _seed_dynamic_server_profile(self) -> str | None:
        dynamic_content = self._build_server_profile_content()
        if not dynamic_content.strip():
            return None

        with NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as handle:
            handle.write(dynamic_content)
            temp_path = Path(handle.name)

        try:
            return self._upsert_document(
                source_path=temp_path,
                original_name="server-profile.md",
                source_uri="starter://server-profile",
                source_container="starter_knowledge",
                source_last_modified_at=datetime.now(UTC).isoformat(),
            )
        finally:
            temp_path.unlink(missing_ok=True)

    def _upsert_document(
        self,
        *,
        source_path: Path,
        original_name: str,
        source_uri: str,
        source_container: str,
        source_last_modified_at: str,
    ) -> str | None:
        try:
            document, action = self.document_service.upsert_external_document(
                file_path=source_path,
                original_name=original_name,
                content_type="text/markdown",
                source_provider="starter_knowledge",
                source_uri=source_uri,
                source_container=source_container,
                source_last_modified_at=source_last_modified_at,
            )
            if action != "skipped":
                self.document_service.queue_document_processing(document.id)

            log_event(
                "starter_knowledge.seed",
                "Starter knowledge document ensured.",
                source_uri=source_uri,
                action=action,
                document_id=document.id,
                document_name=document.original_name,
            )
            return document.id if action != "skipped" else None
        except Exception as exc:  # noqa: BLE001
            log_event(
                "starter_knowledge.seed",
                "Starter knowledge seeding failed.",
                status="warning",
                source_uri=source_uri,
                error=str(exc),
            )
            return None

    def _process_documents_background(self, document_ids: list[str]) -> None:
        for document_id in document_ids:
            try:
                self.document_service.process_document(document_id)
                log_event(
                    "starter_knowledge.process",
                    "Starter knowledge document processed.",
                    document_id=document_id,
                )
            except Exception as exc:  # noqa: BLE001
                log_event(
                    "starter_knowledge.process",
                    "Starter knowledge document processing failed.",
                    status="warning",
                    document_id=document_id,
                    error=str(exc),
                )

    def _build_server_profile_content(self) -> str:
        install_report = self._read_install_report()
        return "\n".join(
            [
                "# Server Profile",
                "",
                "This document describes the current Local AI OS installation on this server.",
                "",
                "## Runtime",
                f"- App name: {settings.app_name}",
                f"- Environment: {settings.app_env}",
                f"- Timezone: {settings.app_timezone}",
                f"- Auth enabled: {'yes' if settings.auth_enabled else 'no'}",
                f"- Safe mode: {'yes' if settings.safe_mode_enabled else 'no'}",
                f"- Starter knowledge enabled: {'yes' if settings.starter_knowledge_enabled else 'no'}",
                "",
                "## AI Services",
                f"- Ollama base URL: {settings.ollama_base_url}",
                f"- Default chat model: {settings.ollama_default_model}",
                f"- Default embedding model: {settings.ollama_embed_model}",
                f"- Qdrant URL: {settings.qdrant_url}",
                f"- Qdrant collection: {settings.qdrant_collection_name}",
                "",
                "## Storage",
                f"- Data root: {settings.data_root}",
                f"- App data root: {settings.app_data_root}",
                f"- Uploads dir: {settings.uploads_dir}",
                f"- Conversations dir: {settings.conversations_dir}",
                f"- Document metadata dir: {settings.documents_metadata_dir}",
                "",
                "## Features",
                f"- OCR enabled: {'yes' if settings.ocr_enabled else 'no'}",
                f"- GLiNER enabled: {'yes' if settings.gliner_enabled else 'no'}",
                "",
                "## Install Report",
                install_report or "No install report was found for this server.",
            ]
        ).strip()

    def _read_install_report(self) -> str:
        latest_report = self.install_dir / "install-report-latest.md"
        if not latest_report.exists():
            return ""

        try:
            return latest_report.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _iso_timestamp_from_path(self, path: Path) -> str:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
