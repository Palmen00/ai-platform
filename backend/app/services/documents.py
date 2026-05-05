import json
import mimetypes
import re
import shutil
from collections import Counter
from datetime import UTC, datetime
import unicodedata
from pathlib import Path
from typing import Any
from uuid import uuid4
from difflib import SequenceMatcher

from fastapi import UploadFile

from app.config import settings
from app.schemas.document import DocumentCommercialLineItem
from app.schemas.document import DocumentCommercialSummary
from app.schemas.document import DocumentRecord
from app.schemas.document import DocumentFacetOption
from app.schemas.document import DocumentFamilyMember
from app.schemas.document import DocumentFamilySummary
from app.schemas.document import DocumentIntelligenceResponse
from app.schemas.document import DocumentIntelligenceSummary
from app.schemas.document import DocumentIntelligenceRefreshResponse
from app.schemas.document import DocumentSignal
from app.schemas.document import DocumentSimilarityMatch
from app.schemas.document import DocumentMaintenanceStatus
from app.schemas.document import DocumentPreview
from app.schemas.document import DocumentPreviewChunk
from app.schemas.chat import ChatHistoryMessage, ChatSource
from app.services.activity import activity_service
from app.services.document_processing import DocumentProcessingService
from app.services.embeddings import EmbeddingService
from app.services.gliner_service import GLiNEREntityService
from app.services.users import UserService
from app.services.vector_store import VectorStoreService


class DocumentService:
    SUPPORTED_UPLOAD_EXTENSIONS = set().union(
        DocumentProcessingService.IMAGE_SUFFIXES,
        DocumentProcessingService.WORD_SUFFIXES,
        DocumentProcessingService.SPREADSHEET_SUFFIXES,
        DocumentProcessingService.PRESENTATION_SUFFIXES,
        DocumentProcessingService.TEXT_SUFFIXES,
        DocumentProcessingService.MARKDOWN_SUFFIXES,
        DocumentProcessingService.JSON_SUFFIXES,
        DocumentProcessingService.CSV_SUFFIXES,
        DocumentProcessingService.CONFIG_SUFFIXES,
        DocumentProcessingService.CODE_SUFFIXES,
        {".pdf"},
    )
    DOCUMENT_TYPE_ALIASES = {
        "invoice": {
            "invoice",
            "invoices",
            "finance",
            "financial",
            "money",
            "faktura",
            "fakturor",
            "fraktura",
            "frakturor",
        },
        "contract": {"contract", "contracts", "agreement", "agreements", "avtal", "kontrakt"},
        "insurance": {"insurance", "insurances", "insurance policy", "insurance policies", "försäkring", "försäkringar"},
        "policy": {"policy", "policies"},
        "roadmap": {"roadmap", "roadmaps"},
        "architecture": {"architecture", "architectures", "arkitektur"},
        "report": {"report", "reports", "rapport", "rapporter"},
        "form": {"form", "forms", "blankett", "blanketter"},
        "receipt": {"receipt", "receipts", "kvitto", "kvitton"},
        "quote": {"quote", "quotes", "quotation", "quotations", "offer", "offers", "offert", "offerter"},
        "features": {"features", "feature", "current features"},
        "word": {"word", "docx", "word document", "document file"},
        "spreadsheet": {"spreadsheet", "spreadsheets", "excel", "worksheet", "worksheets", "sheet", "sheets", "xlsx"},
        "presentation": {
            "presentation",
            "presentations",
            "slides",
            "slide",
            "deck",
            "decks",
            "slide deck",
            "ppt",
            "pptx",
        },
        "code": {"code", "source code", "script", "scripts", "repository", "repo"},
        "config": {"config", "configs", "configuration", "configurations", "settings file", "yaml", "yml", "env"},
        "document": {"document", "documents", "file", "files", "doc", "docs"},
    }

    def __init__(self) -> None:
        self.uploads_dir = settings.uploads_dir
        self.metadata_dir = settings.documents_metadata_dir
        self.deleted_metadata_dir = self.metadata_dir / ".deleted"
        self.chunks_dir = settings.document_chunks_dir
        self.extracted_text_dir = settings.document_extracted_text_dir
        self.processing_service = DocumentProcessingService()
        self.embedding_service = EmbeddingService()
        self.gliner_service = GLiNEREntityService()
        self.user_service = UserService()
        self.vector_store = VectorStoreService()
        self._query_entity_cache: dict[str, list[str]] = {}

    def list_documents(self) -> list[DocumentRecord]:
        documents: list[DocumentRecord] = []

        for metadata_file in sorted(self.metadata_dir.glob("*.json")):
            try:
                with metadata_file.open("r", encoding="utf-8") as file_handle:
                    payload = json.load(file_handle)
                    documents.append(
                        self._enrich_document_metadata(
                            self._normalize_document_record(
                                DocumentRecord.model_validate(payload)
                            )
                        )
                    )
            except (FileNotFoundError, json.JSONDecodeError, ValueError):
                # Keep listing resilient if files are deleted or rewritten mid-iteration.
                continue

        return sorted(documents, key=lambda item: item.uploaded_at, reverse=True)

    def list_documents_for_ui(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        query: str = "",
        status_filter: str = "all",
        type_filter: str = "all",
        source_filter: str = "all",
        sort_order: str = "newest",
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> tuple[
        list[DocumentRecord],
        int,
        list[str],
        list[str],
        list[DocumentFacetOption],
        list[DocumentFacetOption],
    ]:
        documents: list[DocumentRecord] = []
        normalized_offset = max(offset, 0)

        for metadata_file in sorted(self.metadata_dir.glob("*.json")):
            try:
                with metadata_file.open("r", encoding="utf-8") as file_handle:
                    payload = json.load(file_handle)
                    document = self._normalize_document_record(
                        DocumentRecord.model_validate(payload)
                    )
                    documents.append(self._compact_document_record(document))
            except (FileNotFoundError, json.JSONDecodeError, ValueError):
                continue

        visible_documents = self._filter_documents_for_viewer(
            documents,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if not is_admin:
            visible_documents = [
                self._sanitize_document_for_viewer(document)
                for document in visible_documents
            ]

        base_filtered_documents = [
            document
            for document in visible_documents
            if self._matches_document_list_filters(
                document=document,
                query=query,
                status_filter=status_filter,
                type_filter="all",
                source_filter="all",
            )
        ]
        available_types = sorted(
            {
                (document.detected_document_type or "document")
                for document in base_filtered_documents
            }
        )
        available_sources = sorted(
            {
                (document.source_provider or document.source_origin)
                for document in base_filtered_documents
                if (document.source_provider or document.source_origin)
            }
        )
        type_counter = Counter(
            (document.detected_document_type or "document")
            for document in base_filtered_documents
        )
        source_counter = Counter(
            (document.source_provider or document.source_origin)
            for document in base_filtered_documents
            if (document.source_provider or document.source_origin)
        )
        available_type_facets = [
            DocumentFacetOption(value=value, count=count)
            for value, count in sorted(
                type_counter.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]
        available_source_facets = [
            DocumentFacetOption(value=value, count=count)
            for value, count in sorted(
                source_counter.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ]

        filtered_documents = [
            document
            for document in base_filtered_documents
            if self._matches_document_list_filters(
                document=document,
                query="",
                status_filter="all",
                type_filter=type_filter,
                source_filter=source_filter,
            )
        ]
        sorted_documents = sorted(
            filtered_documents,
            key=self._document_list_sort_key(sort_order),
            reverse=self._document_list_sort_reverse(sort_order),
        )
        total_count = len(sorted_documents)
        if limit is None:
            return (
                sorted_documents[normalized_offset:],
                total_count,
                available_types,
                available_sources,
                available_type_facets,
                available_source_facets,
            )

        normalized_limit = max(limit, 1)
        return (
            sorted_documents[
                normalized_offset : normalized_offset + normalized_limit
            ],
            total_count,
            available_types,
            available_sources,
            available_type_facets,
            available_source_facets,
        )

    def list_uploaded_document_names(
        self,
        *,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> list[str]:
        return [
            document.original_name
            for document in self.list_uploaded_documents(
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
        ]

    def list_uploaded_documents(
        self,
        *,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> list[DocumentRecord]:
        return [
            document
            for document in self._filter_documents_for_viewer(
                self.list_documents(),
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
        ]

    def get_extracted_text(self, document_id: str) -> str:
        extracted_path = self.extracted_text_dir / f"{document_id}.txt"
        if not extracted_path.exists():
            return ""
        return extracted_path.read_text(encoding="utf-8")

    def resolve_primary_document(
        self,
        query: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> DocumentRecord | None:
        matched_ids: list[str] = []
        if history and (
            self._looks_like_follow_up_document_question(query)
            or self.is_document_kind_confirmation_query(query)
        ):
            matched_ids = self.resolve_follow_up_document_ids(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
        if not matched_ids:
            matched_ids = self.find_referenced_documents(
                query,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
        if not matched_ids:
            matched_ids = self.resolve_follow_up_document_ids(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
        if not matched_ids:
            return None
        return self.get_document_for_viewer(
            matched_ids[0],
            is_admin=is_admin,
            viewer_username=viewer_username,
        )

    def find_referenced_documents(
        self,
        query: str,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> list[str]:
        normalized_query = self._normalize_document_name(query)
        query_terms = set(self.extract_query_terms(query)) | set(
            self._reference_query_terms(query)
        )
        allowed_document_id_set = set(allowed_document_ids or [])
        exact_matches: list[tuple[float, str]] = []
        ranked_matches: list[tuple[float, str]] = []

        for document in self._filter_documents_for_viewer(
            self.list_documents(),
            is_admin=is_admin,
            viewer_username=viewer_username,
        ):
            if allowed_document_id_set and document.id not in allowed_document_id_set:
                continue

            normalized_name = self._normalize_document_name(document.original_name)
            name_terms = set(re.findall(r"[a-z0-9]{2,}", normalized_name))
            if not normalized_name or not name_terms:
                continue

            phrase_match = 1.0 if normalized_name in normalized_query else 0.0
            exact_stem_match = (
                1.0
                if self._normalize_document_name(Path(document.original_name).stem)
                in normalized_query
                else 0.0
            )
            shared_terms = query_terms & name_terms
            short_reference_bonus = 0.0
            for term in shared_terms:
                if len(term) > 2:
                    continue
                if normalized_name.startswith(f"{term} "):
                    short_reference_bonus = max(short_reference_bonus, 0.36)
                else:
                    short_reference_bonus = max(short_reference_bonus, 0.24)
            overlap_score = (
                len(shared_terms) / max(len(query_terms), 1)
                if query_terms
                else 0.0
            )
            precision_score = (
                len(shared_terms) / max(len(name_terms), 1)
                if name_terms
                else 0.0
            )
            extra_term_penalty = (
                min(len(name_terms - query_terms) * 0.08, 0.2)
                if query_terms
                else 0.0
            )
            similarity_score = SequenceMatcher(
                None,
                normalized_query,
                normalized_name,
            ).ratio()
            metadata_signal_score = self._document_signal_score(
                document=document,
                query=query,
                query_terms=query_terms,
            )
            combined_score = (
                (phrase_match * 0.5)
                + (exact_stem_match * 0.25)
                + (overlap_score * 0.12)
                + (precision_score * 0.08)
                + (similarity_score * 0.05)
                + (metadata_signal_score * 0.18)
                + short_reference_bonus
                - extra_term_penalty
            )

            if combined_score < 0.18:
                continue

            if phrase_match or exact_stem_match:
                exact_matches.append((combined_score, document.id))
            ranked_matches.append((combined_score, document.id))

        if exact_matches:
            exact_matches.sort(key=lambda item: item[0], reverse=True)
            return [document_id for _, document_id in exact_matches]

        ranked_matches.sort(key=lambda item: item[0], reverse=True)
        return [document_id for _, document_id in ranked_matches]

    def resolve_follow_up_document_ids(
        self,
        query: str,
        history: list[ChatHistoryMessage] | None = None,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> list[str]:
        if not history:
            return []

        visible_documents = self.list_uploaded_documents(
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        allowed_document_id_set = set(allowed_document_ids or [])
        visible_document_map = {
            document.id: document
            for document in visible_documents
            if not allowed_document_id_set or document.id in allowed_document_id_set
        }
        if not visible_document_map:
            return []

        candidate_ids: list[str] = []
        constrained_ids = list(visible_document_map.keys())
        for message in reversed(history[-8:]):
            for source in message.sources:
                if (
                    getattr(source, "document_id", None)
                    and source.document_id in visible_document_map
                    and source.document_id not in candidate_ids
                ):
                    candidate_ids.append(source.document_id)

            if not message.content:
                continue

            referenced_ids = self.find_referenced_documents(
                message.content,
                allowed_document_ids=constrained_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            for document_id in referenced_ids[:3]:
                if document_id not in candidate_ids:
                    candidate_ids.append(document_id)

        if not candidate_ids:
            return []

        normalized_query = self._normalize_document_name(query)
        query_terms = set(self._reference_query_terms(query))
        follow_up_question = self._looks_like_follow_up_document_question(query)
        ranked_matches: list[tuple[float, str]] = []

        for index, document_id in enumerate(candidate_ids):
            document = visible_document_map.get(document_id)
            if document is None:
                continue

            normalized_name = self._normalize_document_name(document.original_name)
            name_terms = set(self._reference_query_terms(document.original_name))
            shared_terms = query_terms & name_terms
            evidence_score = 0.0

            if normalized_name and normalized_name in normalized_query:
                evidence_score += 0.9
            if shared_terms:
                evidence_score += min(0.72, len(shared_terms) * 0.38)
            if query_terms and any(term in normalized_name for term in query_terms):
                evidence_score += 0.16
            if query_terms and evidence_score == 0.0:
                continue

            score = evidence_score + max(0.0, 0.18 - (index * 0.02))
            if follow_up_question:
                score += 0.08

            if score >= 0.24:
                ranked_matches.append((score, document_id))

        if ranked_matches:
            ranked_matches.sort(key=lambda item: item[0], reverse=True)
            return [document_id for _, document_id in ranked_matches]

        if follow_up_question and candidate_ids:
            return candidate_ids[:1]

        return []

    def recent_sources_for_document_ids(
        self,
        document_ids: list[str],
        *,
        limit: int = 4,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> list[ChatSource]:
        allowed_document_id_set = set(document_ids)
        processed_documents = [
            document
            for document in self.list_uploaded_documents(
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if document.id in allowed_document_id_set
            and document.processing_status == "processed"
        ]
        return self._recent_sources(processed_documents, limit=limit)

    def save_upload(self, upload: UploadFile) -> DocumentRecord:
        self._validate_upload_name(Path(upload.filename or "document").name)
        return self._store_document_file(
            source_file=upload.file,
            original_name=Path(upload.filename or "document").name,
            content_type=upload.content_type or "application/octet-stream",
            source_origin="upload",
        )

    def import_external_document(
        self,
        *,
        file_path: Path,
        original_name: str | None = None,
        content_type: str = "application/octet-stream",
        source_connector_id: str | None = None,
        source_provider: str | None = None,
        source_uri: str | None = None,
        source_container: str | None = None,
        source_last_modified_at: str | None = None,
        visibility: str = "standard",
        access_usernames: list[str] | None = None,
    ) -> DocumentRecord:
        resolved_name = Path(original_name or file_path.name).name
        with file_path.open("rb") as file_handle:
            return self._store_document_file(
                source_file=file_handle,
                original_name=resolved_name,
                content_type=content_type,
                source_origin="connector" if source_provider or source_uri else "import",
                source_connector_id=source_connector_id,
                source_provider=source_provider,
                source_uri=source_uri,
                source_container=source_container,
                source_last_modified_at=source_last_modified_at,
                visibility=visibility,
                access_usernames=access_usernames,
            )

    def upsert_external_document(
        self,
        *,
        file_path: Path,
        original_name: str | None = None,
        content_type: str | None = None,
        source_connector_id: str | None = None,
        source_provider: str | None = None,
        source_uri: str | None = None,
        source_container: str | None = None,
        source_last_modified_at: str | None = None,
        visibility: str = "standard",
        access_usernames: list[str] | None = None,
    ) -> tuple[DocumentRecord, str]:
        if source_provider and source_uri:
            existing = self.find_document_by_source(
                source_provider=source_provider,
                source_uri=source_uri,
            )
            if existing is not None:
                if (
                    source_last_modified_at
                    and existing.source_last_modified_at == source_last_modified_at
                ):
                    return existing, "skipped"

                updated = self._replace_document_file(
                    document=existing,
                    source_path=file_path,
                    original_name=original_name or file_path.name,
                    content_type=content_type or self._guess_content_type(file_path),
                    source_connector_id=source_connector_id,
                    source_provider=source_provider,
                    source_uri=source_uri,
                    source_container=source_container,
                    source_last_modified_at=source_last_modified_at,
                    visibility=visibility,
                    access_usernames=access_usernames,
                )
                return updated, "updated"

        created = self.import_external_document(
            file_path=file_path,
            original_name=original_name,
            content_type=content_type or self._guess_content_type(file_path),
            source_connector_id=source_connector_id,
            source_provider=source_provider,
            source_uri=source_uri,
            source_container=source_container,
            source_last_modified_at=source_last_modified_at,
            visibility=visibility,
            access_usernames=access_usernames,
        )
        return created, "imported"

    def get_document(self, document_id: str) -> DocumentRecord | None:
        if self._is_document_deleted(document_id):
            return None

        metadata_path = self._metadata_path(document_id)
        if not metadata_path.exists():
            return None

        try:
            with metadata_path.open("r", encoding="utf-8") as file_handle:
                payload = json.load(file_handle)
        except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError):
            return None
        if not isinstance(payload, dict):
            return None

        return self._enrich_document_metadata(
            self._normalize_document_record(DocumentRecord.model_validate(payload))
        )

    def get_document_for_viewer(
        self,
        document_id: str,
        *,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> DocumentRecord | None:
        document = self.get_document(document_id)
        if document is None:
            return None
        if not self._document_is_visible_to_viewer(
            document,
            is_admin=is_admin,
            viewer_username=viewer_username,
        ):
            return None
        if not is_admin:
            return self._sanitize_document_for_viewer(document)
        return document

    def find_document_by_source(
        self,
        *,
        source_provider: str,
        source_uri: str,
    ) -> DocumentRecord | None:
        for document in self.list_documents():
            if (
                (document.source_provider or "") == source_provider
                and (document.source_uri or "") == source_uri
            ):
                return document
        return None

    def predict_external_document_action(
        self,
        *,
        source_provider: str | None,
        source_uri: str | None,
        source_last_modified_at: str | None,
    ) -> tuple[str, str | None]:
        if not source_provider or not source_uri:
            return "imported", None

        existing = self.find_document_by_source(
            source_provider=source_provider,
            source_uri=source_uri,
        )
        if existing is None:
            return "imported", None

        if (
            source_last_modified_at
            and existing.source_last_modified_at == source_last_modified_at
        ):
            return "skipped", existing.id

        return "updated", existing.id

    def update_document_visibility(
        self,
        document_id: str,
        *,
        visibility: str,
        access_usernames: list[str] | None = None,
    ) -> DocumentRecord:
        normalized_visibility = (visibility or "").strip().lower()
        if normalized_visibility not in {"standard", "hidden", "restricted"}:
            raise ValueError(
                "Visibility must be 'standard', 'hidden', or 'restricted'."
            )

        document = self.get_document(document_id)
        if document is None:
            raise FileNotFoundError(f"Document {document_id} not found")

        document.visibility = normalized_visibility
        document.access_usernames = self._normalize_document_access_usernames(
            access_usernames or [],
            visibility=normalized_visibility,
        )
        self._write_metadata(document)
        return document

    def apply_connector_permissions(
        self,
        *,
        connector_id: str,
        visibility: str,
        access_usernames: list[str] | None = None,
        source_provider: str | None = None,
        source_container: str | None = None,
        updated_source_container: str | None = None,
    ) -> int:
        normalized_visibility = self._normalize_document_visibility(visibility)
        normalized_access = self._normalize_document_access_usernames(
            access_usernames or [],
            visibility=normalized_visibility,
        )
        updated_count = 0

        for document in self.list_documents():
            matches_connector = (document.source_connector_id or "") == connector_id
            matches_legacy_source = (
                not matches_connector
                and not document.source_connector_id
                and source_provider is not None
                and source_container is not None
                and (document.source_provider or "") == source_provider
                and (document.source_container or "") == source_container
            )
            if not matches_connector and not matches_legacy_source:
                continue

            if (
                document.source_connector_id == connector_id
                and document.visibility == normalized_visibility
                and document.access_usernames == normalized_access
            ):
                continue

            document.source_connector_id = connector_id
            if updated_source_container is not None:
                document.source_container = updated_source_container
            document.visibility = normalized_visibility
            document.access_usernames = list(normalized_access)
            self._write_metadata(document)
            updated_count += 1

        return updated_count

    def get_document_preview(
        self,
        document_id: str,
        max_characters: int = 4000,
        max_chunks: int = 8,
        focus_chunk_index: int | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> DocumentPreview:
        document = self.get_document_for_viewer(
            document_id,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if document is None:
            raise FileNotFoundError(f"Document {document_id} not found")

        extracted_text = ""
        extracted_text_truncated = False
        extracted_path = self.extracted_text_dir / f"{document_id}.txt"
        if extracted_path.exists():
            full_text = extracted_path.read_text(encoding="utf-8")
            extracted_text_truncated = len(full_text) > max_characters
            extracted_text = full_text[:max_characters]

        preview_chunks: list[DocumentPreviewChunk] = []
        chunks_path = self.chunks_dir / f"{document_id}.json"
        if chunks_path.exists():
            with chunks_path.open("r", encoding="utf-8") as file_handle:
                chunks = json.load(file_handle)

            selected_chunks = chunks[:max_chunks]
            if focus_chunk_index is not None:
                selected_chunks = self._select_preview_chunks(
                    chunks=chunks,
                    focus_chunk_index=focus_chunk_index,
                    max_chunks=max_chunks,
                )

            for chunk in selected_chunks:
                preview_chunks.append(
                    DocumentPreviewChunk(
                        index=int(chunk.get("index", 0)),
                        content=self._normalize_text_fragment(
                            str(chunk.get("content", ""))
                        ),
                        section_title=self._normalize_optional_text(
                            chunk.get("section_title")
                        ),
                        page_number=self._normalize_optional_int(
                            chunk.get("page_number")
                        ),
                    )
                )

        return DocumentPreview(
            document=document,
            extracted_text=self._normalize_text_fragment(extracted_text),
            extracted_text_truncated=extracted_text_truncated,
            chunks=preview_chunks,
            focused_chunk_index=focus_chunk_index,
        )

    def process_document(self, document_id: str) -> DocumentRecord:
        if self._is_document_deleted(document_id):
            raise FileNotFoundError(f"Document {document_id} not found")

        document = self.get_document(document_id)
        if document is None:
            raise FileNotFoundError(f"Document {document_id} not found")

        file_path = self.uploads_dir / document.stored_name
        if not file_path.exists():
            raise FileNotFoundError(f"Stored file missing for document {document_id}")

        activity_service.begin_job("document_processing")
        try:
            self._update_processing_stage(document, "extracting")
            extraction_result = self.processing_service.extract_document(
                file_path=file_path,
                content_type=document.content_type,
            )
            extracted_text = str(extraction_result.get("text", ""))
            self._update_processing_stage(document, "chunking")
            chunks = self.processing_service.chunk_text(
                extracted_text,
                document_name=document.original_name,
                content_type=document.content_type,
                file_path=file_path,
            )

            document.processing_status = "processed"
            document.ocr_used = bool(extraction_result.get("ocr_used", False))
            document.ocr_status = str(extraction_result.get("ocr_status", "not_needed"))
            document.ocr_engine = (
                str(extraction_result.get("ocr_engine"))
                if extraction_result.get("ocr_engine")
                else None
            )
            document.ocr_error = (
                str(extraction_result.get("ocr_error"))
                if extraction_result.get("ocr_error")
                else None
            )
            document.character_count = len(extracted_text)
            document.chunk_count = len(chunks)
            document.document_title = self.processing_service.detect_document_title(
                extracted_text,
                document.original_name,
                content_type=document.content_type,
                file_path=file_path,
            )
            document.source_kind = self.processing_service.detect_source_kind(
                document.original_name,
                document.content_type,
            )
            document.section_count = len(
                {
                    str(chunk.get("section_title", "")).strip()
                    for chunk in chunks
                    if str(chunk.get("section_title", "")).strip()
                }
            )
            document.detected_document_type = self.processing_service.detect_document_type(
                extracted_text,
                document.original_name,
                document.content_type,
            )
            document.document_entities = self.processing_service.detect_document_entities(
                extracted_text,
                document.original_name,
                document.detected_document_type,
            )
            document.document_signals = self.processing_service.detect_document_signals(
                extracted_text,
                document.original_name,
                document.detected_document_type,
                document.document_title,
                document.document_entities,
            )
            document.document_signals = self._coerce_document_signals(document.document_signals)
            (
                document.document_date,
                document.document_date_label,
                document.document_date_kind,
            ) = self.processing_service.detect_document_date(
                extracted_text,
                document.original_name,
                document.detected_document_type,
            )
            document.commercial_summary = self.processing_service.extract_commercial_summary(
                extracted_text,
                document.original_name,
                document.detected_document_type,
            )
            document.document_family_key = self._derive_document_family_key(document)
            document.document_family_label = self._derive_document_family_label(document)
            (
                document.document_version_label,
                document.document_version_number,
            ) = self._derive_document_version(document)
            document.document_topics = self._build_document_topics(
                document,
                extracted_text=extracted_text,
            )
            document.document_summary_anchor = self._derive_document_summary_anchor(
                document,
                extracted_text=extracted_text,
            )
            document.last_processed_at = datetime.now(UTC).isoformat()
            document.processing_error = None

            self._write_extracted_text(document.id, extracted_text)
            self._write_chunks(document.id, chunks)

            if chunks:
                try:
                    self._update_processing_stage(document, "indexing")
                    embeddings = self.embedding_service.embed_texts(
                        [str(chunk.get("content", "")) for chunk in chunks]
                    )
                    self.vector_store.remove_document_chunks(document.id)
                    self.vector_store.index_document_chunks(
                        document=document,
                        chunks=chunks,
                        embeddings=embeddings,
                    )
                    document.processing_status = "processed"
                    document.indexing_status = "indexed"
                    document.indexed_at = datetime.now(UTC).isoformat()
                    document.indexing_error = None
                    document.processing_stage = "completed"
                    document.processing_updated_at = datetime.now(UTC).isoformat()
                except Exception as exc:
                    document.processing_status = "processed"
                    document.indexing_status = "failed"
                    document.indexed_at = None
                    document.indexing_error = str(exc)
                    document.processing_stage = "failed"
                    document.processing_updated_at = datetime.now(UTC).isoformat()
            else:
                document.processing_status = "processed"
                document.indexing_status = "skipped"
                document.indexed_at = None
                document.indexing_error = document.ocr_error or (
                    "No extractable text was found. Scanned or handwritten PDFs may require OCR."
                )
                document.processing_stage = "completed"
                document.processing_updated_at = datetime.now(UTC).isoformat()

            try:
                self._refresh_similarity_cache_for_document(
                    document,
                    extracted_text=extracted_text,
                )
            except Exception:
                document.similarity_profile = self._build_document_similarity_profile(
                    document,
                    sample_text=extracted_text,
                )
                document.similarity_terms = self._build_similarity_terms(
                    document,
                    extracted_text=extracted_text,
                )
                document.similarity_updated_at = datetime.now(UTC).isoformat()
        except Exception as exc:
            document.processing_status = "failed"
            document.ocr_used = False
            document.ocr_status = "failed"
            document.ocr_engine = None
            document.ocr_error = None
            document.character_count = 0
            document.chunk_count = 0
            document.document_title = None
            document.source_kind = None
            document.section_count = 0
            document.detected_document_type = None
            document.document_entities = []
            document.document_signals = []
            document.document_date = None
            document.document_date_label = None
            document.document_date_kind = None
            document.document_family_key = None
            document.document_family_label = None
            document.document_version_label = None
            document.document_version_number = None
            document.document_topics = []
            document.document_summary_anchor = None
            document.commercial_summary = None
            document.similarity_profile = None
            document.similarity_terms = []
            document.similar_documents = []
            document.similarity_updated_at = None
            document.last_processed_at = datetime.now(UTC).isoformat()
            document.processing_error = str(exc)
            document.processing_stage = "failed"
            document.processing_updated_at = datetime.now(UTC).isoformat()
            document.indexing_status = "pending"
            document.indexed_at = None
            document.indexing_error = None
            self._remove_processing_artifacts(document.id)
        finally:
            activity_service.end_job("document_processing")

        if self._is_document_deleted(document.id):
            self._remove_processing_artifacts(document.id)
            try:
                self.vector_store.remove_document_chunks(document.id)
            except Exception:
                pass
            return document

        self._write_metadata(document)
        return document

    def backfill_document_intelligence(
        self,
        *,
        limit: int = 1,
    ) -> list[DocumentRecord]:
        refreshed_documents: list[DocumentRecord] = []
        max_items = max(limit, 1)

        for document in self.list_documents():
            if not self._needs_background_intelligence_refresh(document):
                continue

            extracted_path = self.extracted_text_dir / f"{document.id}.txt"
            if not extracted_path.exists():
                continue

            extracted_text = extracted_path.read_text(encoding="utf-8")
            activity_service.begin_job("document_intelligence")
            try:
                document = self._enrich_document_metadata(document)
                self._refresh_similarity_cache_for_document(
                    document,
                    extracted_text=extracted_text,
                )
                self._write_metadata(document)
                refreshed_documents.append(document)
            finally:
                activity_service.end_job("document_intelligence")

            if len(refreshed_documents) >= max_items:
                break

        return refreshed_documents

    def count_background_intelligence_backlog(self) -> int:
        return sum(
            1
            for document in self.list_documents()
            if self._needs_background_intelligence_refresh(document)
        )

    def get_document_intelligence_status(
        self,
        *,
        maintenance_status: DocumentMaintenanceStatus | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> DocumentIntelligenceResponse:
        visible_documents = self._filter_documents_for_viewer(
            self.list_documents(),
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        processed_documents = [
            document
            for document in visible_documents
            if document.processing_status == "processed"
        ]
        stale_documents = [
            document
            for document in processed_documents
            if self._needs_background_intelligence_refresh(document)
        ]
        family_summaries = self._build_family_summaries(processed_documents)
        return DocumentIntelligenceResponse(
            summary=DocumentIntelligenceSummary(
                total_documents=len(visible_documents),
                processed_documents=len(processed_documents),
                profile_ready_documents=sum(
                    1 for document in processed_documents if document.similarity_profile
                ),
                family_ready_documents=sum(
                    1 for document in processed_documents if document.document_family_key
                ),
                versioned_documents=sum(
                    1 for document in processed_documents if document.document_version_label
                ),
                topic_ready_documents=sum(
                    1 for document in processed_documents if document.document_topics
                ),
                total_families=len(family_summaries),
                stale_documents=len(stale_documents),
            ),
            maintenance=maintenance_status or DocumentMaintenanceStatus(),
            families=family_summaries[:8],
            stale_documents=[
                DocumentFamilyMember(
                    document_id=document.id,
                    document_name=document.original_name,
                    document_date=document.document_date,
                    version_label=document.document_version_label,
                    uploaded_at=document.uploaded_at,
                )
                for document in stale_documents[:8]
            ],
        )

    def queue_document_processing(self, document_id: str) -> DocumentRecord:
        document = self.get_document(document_id)
        if document is None:
            raise FileNotFoundError(f"Document {document_id} not found")

        self._update_processing_stage(
            document,
            "queued",
            reset_started_at=True,
        )
        return document

    def queue_all_documents_processing(self) -> list[DocumentRecord]:
        queued_documents: list[DocumentRecord] = []

        for document in self.list_documents():
            queued_documents.append(
                self.queue_document_processing(document.id)
            )

        return queued_documents

    def delete_document(self, document_id: str) -> bool:
        document = self.get_document(document_id)
        if document is None:
            return False

        self._mark_document_deleted(document_id)
        metadata_path = self._metadata_path(document_id)
        file_path = self.uploads_dir / document.stored_name
        if file_path.exists():
            file_path.unlink()

        self._remove_processing_artifacts(document_id)
        try:
            self.vector_store.remove_document_chunks(document_id)
        except Exception:
            pass
        metadata_path.unlink(missing_ok=True)
        return True

    def retry_incomplete_documents(self) -> list[DocumentRecord]:
        retried_documents: list[DocumentRecord] = []

        for document in self.list_documents():
            if not self.is_document_retriable(document):
                continue

            retried_documents.append(self.process_document(document.id))

        return retried_documents

    def count_retriable_documents(self) -> int:
        return sum(
            1 for document in self.list_documents() if self.is_document_retriable(document)
        )

    def list_visible_document_ids(
        self,
        *,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> list[str]:
        return [
            document.id
            for document in self._filter_documents_for_viewer(
                self.list_documents(),
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
        ]

    def is_document_retriable(self, document: DocumentRecord) -> bool:
        if document.processing_status != "processed":
            return False

        return document.indexing_status != "indexed"

    def search_chunks(
        self,
        query: str,
        limit: int = 4,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> list[ChatSource]:
        terms = self.extract_query_terms(query)
        allowed_document_id_set = set(allowed_document_ids or [])
        processed_documents = [
            document
            for document in self._filter_documents_for_viewer(
                self.list_documents(),
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if document.processing_status == "processed"
            and (
                not allowed_document_id_set or document.id in allowed_document_id_set
            )
        ]

        if not terms:
            if self._should_use_recent_document_fallback(query, processed_documents):
                return self._recent_sources(processed_documents, limit=limit)
            return []

        ranked_sources: list[ChatSource] = []

        for document in processed_documents:
            chunks_path = self.chunks_dir / f"{document.id}.json"
            if not chunks_path.exists():
                continue

            with chunks_path.open("r", encoding="utf-8") as file_handle:
                chunks = json.load(file_handle)

            signal_bonus = self._document_signal_bonus(
                document=document,
                query=query,
                query_terms=set(terms),
            )

            for chunk in chunks:
                content = str(chunk.get("content", ""))
                score = self._score_chunk(content, terms)
                if score <= 0:
                    continue

                combined_score = score + signal_bonus

                ranked_sources.append(
                    ChatSource(
                        document_id=document.id,
                        document_name=document.original_name,
                        chunk_index=int(chunk.get("index", 0)),
                        score=combined_score,
                        excerpt=content[:280],
                        section_title=self._normalize_optional_text(
                            chunk.get("section_title")
                        ),
                        page_number=self._normalize_optional_int(
                            chunk.get("page_number")
                        ),
                        source_kind=self._normalize_optional_text(
                            chunk.get("source_kind")
                        ),
                        ocr_used=bool(document.ocr_used),
                    )
                )

        ranked_sources.sort(key=lambda item: item.score, reverse=True)
        if ranked_sources:
            return ranked_sources[:limit]

        if self._should_use_recent_document_fallback(query, processed_documents):
            return self._recent_sources(processed_documents, limit=limit)

        return []

    def is_document_reference_query(self, query: str) -> bool:
        lowered = query.lower()
        reference_terms = {
            "file",
            "files",
            "doc",
            "docs",
            "document",
            "documents",
            "report",
            "reports",
            "policy",
            "policies",
            "contract",
            "contracts",
            "agreement",
            "agreements",
            "invoice",
            "invoices",
            "finance",
            "financial",
            "money",
            "spreadsheet",
            "spreadsheets",
            "worksheet",
            "worksheets",
            "sheet",
            "sheets",
            "presentation",
            "presentations",
            "deck",
            "decks",
            "slide",
            "slides",
            "scan",
            "scanned",
            "ocr",
            "code",
            "script",
            "uploaded",
            "upload",
            "pdf",
            "fil",
            "filer",
            "dokument",
            "uppladdad",
            "uppladdade",
            "arkitekturfilen",
        }
        if any(term in lowered for term in reference_terms):
            return True
        return bool(
            re.search(
                r"\.(?:pdf|txt|md|docx?|xlsx?|pptx?|csv|json|xml|ya?ml|py|ts|tsx|js|jsx|png|jpe?g)\b",
                lowered,
            )
        )

    def is_document_inventory_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        inventory_markers = (
            "what files have i uploaded",
            "what kind of files have i uploaded",
            "what kinds of files have i uploaded",
            "what kinda files have i uploaded",
            "which files have i uploaded",
            "what documents have i uploaded",
            "which documents have i uploaded",
            "list uploaded files",
            "list uploaded documents",
            "list my files",
            "list my documents",
            "show my files",
            "show my documents",
            "visa mina filer",
            "vilka filer har jag laddat upp",
            "vilka dokument har jag laddat upp",
        )
        if any(marker in lowered for marker in inventory_markers):
            return True

        if re.search(
            r"\b(?:what|which)\s+(?:files?|documents?)\b.*\b(?:upload|uploaded)\b",
            lowered,
        ):
            return True
        if re.search(
            r"\blist\s+(?:the\s+)?uploaded\s+(?:files?|documents?)\b",
            lowered,
        ):
            return True
        if re.search(
            r"\bwhat\s+(?:kind|kinds|kinda)\s+of\s+(?:files?|documents?)\b.*\b(?:upload|uploaded)\b",
            lowered,
        ):
            return True

        if self.is_recent_document_inventory_query(query) and any(
            marker in lowered
            for marker in ("upload", "uploaded", "file", "files", "document", "documents")
        ):
            return True

        return False

    def is_recent_document_inventory_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        recent_markers = (
            "latest",
            "lataste",
            "most recent",
            "newest",
            "last uploaded",
            "recently uploaded",
            "senaste",
            "nyaste",
            "senast uppladdade",
            "sist uppladdade",
        )
        return any(marker in lowered for marker in recent_markers) or bool(
            re.search(r"\b(?:upload|uploaded)\s+last\b|\blast\s+(?:upload|uploaded)\b", lowered)
        )

    def is_document_metadata_inventory_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        if not (
            self.extract_requested_document_type(query)
            or self.extract_requested_document_year(query)
            or self.extract_requested_document_entity(query)
        ):
            return False

        if re.search(
            r"\bwhat\s+(files|documents|invoices|contracts|agreements|policies|roadmaps|reports|forms|receipts|quotes)\b",
            lowered,
        ):
            return True
        if re.search(
            r"\b(?:vilka|visa|har jag|finns det)\s+(?:mina\s+)?(?:filer|dokument|fakturor|frakturor|avtal|kontrakt|policyer|roadmaps|rapporter|blanketter|kvitton|offerter)\b",
            lowered,
        ):
            return True

        inventory_markers = (
            "which ",
            "show ",
            "list ",
            "find ",
            "search ",
            "filter ",
            "do i have",
            "do we have",
            "have i",
            "have we",
            "any ",
            "my ",
            "uploaded",
            "har jag",
            "finns det",
            "visa ",
            "vilka ",
            "mina ",
        )
        if any(marker in lowered for marker in inventory_markers):
            return True

        return False

    def is_document_content_question(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        content_markers = (
            "mention",
            "mentions",
            "mentioned",
            "summarize",
            "summary",
            "explain",
            "explains",
            "explained",
            "say about",
            "says about",
            "what does",
            "what do",
            "covers",
            "cover",
            "describe",
            "describes",
            "about",
            "contains",
            "contain",
            "company",
            "vendor",
            "supplier",
            "customer",
            "products",
            "product",
            "items",
            "item",
            "ordered",
            "did i order",
            "risk",
            "risks",
            "issue",
            "issues",
            "incident",
            "incidents",
            "action",
            "actions",
            "todo",
            "deadline",
            "deadlines",
            "due",
            "decision",
            "decisions",
            "amount",
            "amounts",
            "money",
            "financial",
            "finance",
            "number",
            "numbers",
            "value",
            "values",
            "total",
            "totals",
            "metric",
            "metrics",
        )
        return any(marker in lowered for marker in content_markers)

    def _looks_like_follow_up_document_question(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        if self.is_document_content_question(query):
            return True
        if any(
            marker in lowered
            for marker in (
                "from what",
                "which company",
                "what company",
                "what vendor",
                "what supplier",
                "what products",
                "what product",
                "what items",
                "what did i order",
                "ordered",
                "asked about before",
                "asked before",
                "other invoices",
                "check again",
                "that invoice",
                "that document",
                "this invoice",
                "this document",
                "before",
            )
        ):
            return True
        return bool(
            re.search(
                r"\b(?:it|that|this|them|those|den|det|denna|detta|dem)\b",
                lowered,
            )
        )

    def is_document_entity_inventory_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        if not self.extract_requested_document_type(query):
            return False

        role_markers = (
            "company",
            "companies",
            "customer",
            "customers",
            "vendor",
            "vendors",
            "supplier",
            "suppliers",
            "client",
            "clients",
            "organization",
            "organisation",
            "organisations",
            "party",
            "parties",
        )
        context_markers = (
            "appears in",
            "appear in",
            "is in",
            "are in",
            "listed in",
            "listed on",
            "mentioned in",
            "mentions",
            "named in",
            "on the",
            "in the",
            "in a",
            "on a",
        )

        return any(marker in lowered for marker in role_markers) and any(
            marker in lowered for marker in context_markers
        )

    def is_document_similarity_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        similarity_markers = (
            "similar",
            "simular",
            "liknande",
            "kinda like",
            "kind of like",
            "looks like",
            "same",
            "duplicates",
            "duplicate",
            "overlap",
        )
        return self.is_document_reference_query(query) and any(
            marker in lowered for marker in similarity_markers
        )

    def is_document_version_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        if "short version" in lowered:
            return False
        version_markers = (
            "latest version",
            "newest version",
            "current version",
            "which version",
            "version of",
            "latest policy",
            "senaste version",
            "nyaste version",
            "gallande version",
        )
        return self.is_document_reference_query(query) and any(
            marker in lowered for marker in version_markers
        )

    def is_document_change_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        change_markers = (
            "what changed",
            "what changed between",
            "difference between",
            "differences between",
            "compare",
            "compare versions",
            "changed between",
            "same or different",
            "basically the same",
            "different",
            "what is different",
            "ändrades",
            "skillnad",
            "jämför",
        )
        return self.is_document_reference_query(query) and any(
            marker in lowered for marker in change_markers
        )

    def is_document_conflict_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        conflict_markers = (
            "conflict",
            "conflicts",
            "contradict",
            "contradiction",
            "mismatch",
            "inconsistent",
            "disagree",
            "motstrid",
            "konflikt",
        )
        return self.is_document_reference_query(query) and any(
            marker in lowered for marker in conflict_markers
        )

    def is_document_topic_presence_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        presence_markers = (
            "contain",
            "contains",
            "mention",
            "mentions",
            "include",
            "includes",
            "talk about",
            "talks about",
            "say about",
            "says about",
            "refer to",
            "references",
        )
        return self.is_document_reference_query(query) and any(
            marker in lowered for marker in presence_markers
        )

    def is_document_type_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        type_markers = (
            "what kind of document",
            "what kind of scanned document",
            "what type of document",
            "what type of scanned document",
            "what is this document",
            "what is the document",
        )
        return self.is_document_reference_query(query) and any(
            marker in lowered for marker in type_markers
        )

    def is_largest_document_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        size_markers = (
            "largest",
            "biggest",
            "storst",
            "storsta",
        )
        return any(marker in lowered for marker in size_markers) and any(
            marker in lowered
            for marker in ("file", "files", "document", "documents", "uploaded", "upload")
        )

    def is_document_upload_time_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        if "upload" not in lowered and "uploaded" not in lowered:
            return False
        if "when" in lowered:
            return True
        return any(
            marker in lowered
            for marker in (
                "what time",
                "which date",
                "vilket datum",
                "nar laddade",
                "när laddade",
            )
        )

    def is_signed_document_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        signature_markers = (
            "signed",
            "signature",
            "signatures",
            "underskr",
            "signerad",
            "signerat",
        )
        return any(marker in lowered for marker in signature_markers) and any(
            marker in lowered
            for marker in ("file", "files", "document", "documents", "uploaded", "upload", "have i", "do i have", "mina", "dokument")
        )

    def is_document_kind_confirmation_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        requested_type = self.extract_requested_document_type(query)
        if not requested_type:
            return False
        if self.is_document_metadata_inventory_query(query):
            return False
        if self.is_document_entity_detail_query(query):
            return False
        if self.is_document_product_query(query):
            return False
        if re.search(r"^\s*(?:is|was|are|were)\b", lowered):
            return True
        return any(
            marker in lowered
            for marker in (
                "asked about before",
                "asked before",
                "the one before",
                "the document before",
                "the one i asked about before",
                "the document i asked about before",
                "then is",
                "then the document",
                "is it ",
                "was it ",
            )
        )

    def is_document_entity_detail_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        role_markers = (
            "company",
            "vendor",
            "supplier",
            "seller",
            "customer",
            "client",
            "organization",
            "organisation",
            "party",
        )
        return any(marker in lowered for marker in role_markers)

    def is_document_product_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        if any(
            marker in lowered
            for marker in (
                "action item",
                "action items",
                "next step",
                "next steps",
                "todo",
                "to do",
            )
        ):
            return False
        product_markers = (
            "product",
            "products",
            "item",
            "items",
            "order",
            "ordered",
            "buy",
            "bought",
            "purchase",
            "purchased",
            "cost",
            "costs",
            "price",
            "prices",
            "bestallt",
            "beställd",
            "bestalld",
            "beställda",
            "bestallda",
            "köpt",
            "kopt",
            "kostnad",
            "kostnader",
            "line item",
            "did i order",
        )
        return any(marker in lowered for marker in product_markers)

    def is_document_invoice_facts_query(self, query: str) -> bool:
        lowered = " ".join(self._strip_accents(query).lower().split())
        fact_markers = (
            "invoice number",
            "invoice no",
            "invoice date",
            "due date",
            "subtotal",
            "tax",
            "total",
            "amount",
            "fakturanummer",
            "fakturadatum",
            "forfallodatum",
            "summa",
            "moms",
        )
        has_invoice_context = (
            "invoice" in lowered
            or "faktura" in lowered
            or self.extract_requested_document_type(query) in {"invoice", "receipt", "quote"}
        )
        return has_invoice_context and any(marker in lowered for marker in fact_markers)

    def is_document_code_function_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        if "function" not in lowered:
            return False
        markers = (
            "function name",
            "function names",
            "what function",
            "which function",
            "functions are",
            "functions appear",
            "function appears",
            "function returns",
        )
        return any(marker in lowered for marker in markers)

    def is_multi_document_product_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        if not self.is_document_product_query(query):
            return False
        if not self.extract_requested_document_type(query):
            return False
        return any(
            marker in lowered
            for marker in (
                "other ",
                "all ",
                "across ",
                "among ",
                "multiple ",
                "many ",
                "any invoices",
                "any documents",
            )
        )

    def is_document_risk_query(self, query: str) -> bool:
        lowered = " ".join(self._strip_accents(query).lower().split())
        if any(
            marker in lowered
            for marker in (
                "incident code",
                "what code",
                "which code",
                "code appears",
                "access code",
            )
        ):
            return False
        markers = (
            "risk",
            "risks",
            "issue",
            "issues",
            "incident",
            "incidents",
            "problem",
            "problems",
            "blocker",
            "blockers",
            "vulnerability",
            "concern",
            "concerns",
            "weakness",
            "weaknesses",
            "risker",
            "problem",
            "incident",
        )
        return any(marker in lowered for marker in markers)

    def is_document_action_query(self, query: str) -> bool:
        lowered = " ".join(self._strip_accents(query).lower().split())
        if re.search(r"\bwhat should i know\b", lowered):
            return False
        markers = (
            "action",
            "actions",
            "action item",
            "action items",
            "todo",
            "to do",
            "next step",
            "next steps",
            "follow up",
            "recommendation",
            "recommendations",
            "what should",
            "what must",
            "atgard",
            "atgarder",
            "nasta steg",
            "ansvarig",
        )
        return any(marker in lowered for marker in markers)

    def is_document_decision_query(self, query: str) -> bool:
        lowered = " ".join(self._strip_accents(query).lower().split())
        markers = (
            "decision",
            "decisions",
            "decided",
            "approved",
            "approval",
            "accepted",
            "rejected",
            "agreed",
            "chosen",
            "selected",
            "go/no-go",
            "beslut",
            "beslutade",
            "godkand",
        )
        return any(marker in lowered for marker in markers)

    def is_document_deadline_query(self, query: str) -> bool:
        lowered = " ".join(self._strip_accents(query).lower().split())
        markers = (
            "deadline",
            "deadlines",
            "due",
            "due date",
            "valid until",
            "expires",
            "expiry",
            "renewal",
            "within",
            "how long",
            "when must",
            "when should",
            "senast",
            "deadline",
            "forfall",
            "giltig",
        )
        return any(marker in lowered for marker in markers)

    def is_broad_similarity_inventory_query(self, query: str) -> bool:
        return self.is_document_similarity_query(query) and not self._reference_query_terms(query)

    def extract_query_terms(self, query: str) -> list[str]:
        return self._query_terms(query)

    def extract_topic_terms(self, query: str, sources: list[ChatSource]) -> list[str]:
        query_terms = self.extract_query_terms(query)
        if not query_terms:
            return []

        topic_phrase = self.extract_topic_phrase(query)
        if topic_phrase:
            phrase_terms = self._query_terms(topic_phrase)
            if phrase_terms:
                return phrase_terms

        focus_terms = self.extract_focus_terms(query)
        if focus_terms:
            prioritized_focus_terms = [
                term for term in focus_terms if term in query_terms
            ]
            if prioritized_focus_terms:
                return prioritized_focus_terms

        if not sources:
            return query_terms

        matched_terms: list[str] = []
        for term in query_terms:
            if any(term in source.excerpt.lower() for source in sources):
                matched_terms.append(term)

        return matched_terms or query_terms

    def extract_topic_phrase(self, query: str) -> str | None:
        lowered = " ".join(self._strip_accents(query).lower().split())
        patterns = (
            r"\b(?:mention|mentions|mentioned)\s+(.+?)(?:\?|$)",
            r"\b(?:contain|contains|contained)\s+(.+?)(?:\?|$)",
            r"\b(?:include|includes|included)\s+(.+?)(?:\?|$)",
            r"\b(?:refer to|references)\s+(.+?)(?:\?|$)",
            r"\b(?:talk about|talks about)\s+(.+?)(?:\?|$)",
            r"\b(?:say about|says about)\s+(.+?)(?:\?|$)",
        )

        for pattern in patterns:
            match = re.search(pattern, lowered)
            if not match:
                continue

            candidate = match.group(1).strip(" ?!.,:;")
            candidate = re.split(
                r"\b(?:in my documents|among my documents|among your uploaded documents|in your uploaded documents|i mina dokument|bland mina dokument)\b",
                candidate,
                maxsplit=1,
            )[0].strip(" ?!.,:;")
            candidate = re.sub(r"^(?:any|några|någon)\s+", "", candidate).strip()
            if not candidate:
                continue
            if len(candidate.split()) >= 2 or len(candidate) >= 5:
                return candidate

        return None

    def extract_focus_terms(self, query: str) -> list[str]:
        lowered = " ".join(query.lower().split())
        patterns = (
            r"\babout\s+([a-z0-9\s_-]+)",
            r"\bom\s+([a-z0-9\s_-]+)",
        )

        for pattern in patterns:
            match = re.search(pattern, lowered)
            if not match:
                continue

            return self._query_terms(match.group(1))

        return []

    def extract_requested_document_type(self, query: str) -> str | None:
        lowered = " ".join(query.lower().split())
        matches: list[tuple[int, int, str]] = []
        ignored_code_phrases = (
            "incident code",
            "access code",
            "error code",
            "status code",
            "postal code",
            "zip code",
            "country code",
            "discount code",
            "tracking code",
            "reference code",
        )
        scanned_media_markers = (
            "scanned pdf",
            "scanned image",
            "scanned photo",
            "ocr",
            ".pdf",
            ".png",
            ".jpg",
            ".jpeg",
            ".tiff",
            ".bmp",
        )
        for document_type, aliases in self.DOCUMENT_TYPE_ALIASES.items():
            if document_type == "document":
                continue
            for alias in aliases:
                match = re.search(rf"\b{re.escape(alias)}\b", lowered)
                if not match:
                    continue
                if document_type == "code" and any(
                    phrase in lowered for phrase in ignored_code_phrases
                ):
                    continue
                if document_type == "code" and any(
                    marker in lowered for marker in scanned_media_markers
                ):
                    continue
                matches.append((match.start(), -len(alias), document_type))

        if not matches:
            return None

        matches.sort()
        return matches[0][2]

    def extract_requested_document_year(self, query: str) -> int | None:
        match = re.search(r"\b(20\d{2}|19\d{2})\b", query)
        if not match:
            return None
        return int(match.group(1))

    def extract_requested_document_entity(self, query: str) -> str | None:
        lowered = " ".join(self._strip_accents(query).lower().split())
        markers = (" från ", " fran ", " from ", " vendor ", " supplier ", " seller ", " company ", " leverantör ")

        for marker in markers:
            index = lowered.find(marker)
            if index < 0:
                continue

            candidate = lowered[index + len(marker) :].strip(" ?!.,:")
            candidate = re.split(
                r"\b(?:in my documents|among my documents|among your uploaded documents|in your uploaded documents|i mina dokument|bland mina dokument|do i have|have i|what|which|show|list|search|filter)\b",
                candidate,
                maxsplit=1,
            )[0].strip(" ?!.,:")
            candidate = re.sub(r"^(?:några|någon|any)\s+", "", candidate).strip()
            if re.search(
                r"\b(?:appear|appears|appearing|listed|mentioned|named|shown|contain|contains)\b",
                candidate,
            ):
                continue
            normalized = self._normalize_entity_text(candidate)
            if not normalized or not re.search(r"[a-z]", normalized):
                continue
            generic_document_reference = re.sub(
                r"^(?:this|that|these|those|the|a|an|den|det|denna|detta)\s+",
                "",
                normalized,
            )
            document_type_aliases = {
                self._normalize_entity_text(alias)
                for aliases in self.DOCUMENT_TYPE_ALIASES.values()
                for alias in aliases
            }
            if generic_document_reference in document_type_aliases:
                continue
            if normalized in {"my documents", "mina dokument", "documents", "dokument"}:
                continue
            return normalized

        return None

    def extract_query_entities(self, query: str) -> list[str]:
        cached = self._query_entity_cache.get(query)
        if cached is not None:
            return cached

        candidates: list[str] = []
        requested_entity = self.extract_requested_document_entity(query)
        if requested_entity:
            candidates.append(requested_entity)

        if self.gliner_service.enabled():
            for candidate_text, _label, _score in self.gliner_service.extract_candidate_entities(query):
                normalized = self._normalize_entity_text(candidate_text)
                if normalized and normalized not in candidates:
                    candidates.append(normalized)

        topic_phrase = self.extract_topic_phrase(query)
        if topic_phrase and len(topic_phrase.split()) >= 2:
            normalized_phrase = self._normalize_entity_text(topic_phrase)
            if normalized_phrase and normalized_phrase not in candidates:
                candidates.append(normalized_phrase)

        limited_candidates = candidates[:4]
        self._query_entity_cache[query] = limited_candidates
        return limited_candidates

    def find_documents_by_metadata(
        self,
        query: str,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> list[DocumentRecord]:
        requested_type = self.extract_requested_document_type(query)
        requested_year = self.extract_requested_document_year(query)
        requested_entity = self.extract_requested_document_entity(query)
        if not requested_entity and self.is_document_metadata_inventory_query(query):
            query_entities = self.extract_query_entities(query)
            if len(query_entities) == 1:
                requested_entity = query_entities[0]
        if not requested_type and not requested_year and not requested_entity:
            return []
        allowed_document_id_set = set(allowed_document_ids or [])
        matches: list[DocumentRecord] = []

        for document in self._filter_documents_for_viewer(
            self.list_documents(),
            is_admin=is_admin,
            viewer_username=viewer_username,
        ):
            if allowed_document_id_set and document.id not in allowed_document_id_set:
                continue

            if requested_type and not self._document_matches_requested_type(
                document,
                requested_type,
            ):
                continue

            if requested_year:
                if not document.document_date or not document.document_date.startswith(str(requested_year)):
                    continue

            if requested_entity and not self._document_matches_entity(document, requested_entity):
                continue

            matches.append(document)

        matches.sort(
            key=lambda document: self._metadata_match_sort_key(
                document,
                requested_type=requested_type,
                requested_entity=requested_entity,
            ),
            reverse=True,
        )
        return matches

    def summarize_documents_by_metadata(
        self,
        query: str,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        requested_type = self.extract_requested_document_type(query)
        requested_year = self.extract_requested_document_year(query)
        requested_entity = self.extract_requested_document_entity(query)
        if not requested_type and not requested_year and not requested_entity:
            return None

        matching_documents = self.find_documents_by_metadata(
            query,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        type_label = self._format_document_type_label(requested_type) if requested_type else "documents"
        year_suffix = f" from {requested_year}" if requested_year else ""
        entity_suffix = ""
        if requested_entity:
            preposition = " from " if requested_type in {"invoice", "quote", "receipt"} else " related to "
            entity_suffix = f"{preposition}{self._format_entity_label(requested_entity)}"

        if not matching_documents:
            return (
                f"I could not find any {type_label}{year_suffix}{entity_suffix} among your uploaded documents."
            )

        if len(matching_documents) == 1:
            document = matching_documents[0]
            date_fragment = f" ({document.document_date_label})" if document.document_date_label else ""
            entity_fragment = self._document_entity_fragment(document, requested_entity)
            return (
                f"I found one {type_label.rstrip('s')}{year_suffix}{entity_suffix}: "
                f"{document.original_name}{date_fragment}{entity_fragment}."
            )

        leading_documents = ", ".join(
            f"{document.original_name}"
            f"{f' ({document.document_date})' if document.document_date else ''}"
            f"{self._document_entity_fragment(document, requested_entity, prefix=' - ')}"
            for document in matching_documents[:4]
        )
        if len(matching_documents) <= 4:
            return (
                f"I found {len(matching_documents)} {type_label}{year_suffix}{entity_suffix}: "
                f"{leading_documents}."
            )

        return (
            f"I found {len(matching_documents)} {type_label}{year_suffix}{entity_suffix}. "
            f"The first few are {leading_documents}, and {len(matching_documents) - 4} more."
        )

    def is_document_title_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        title_markers = ("title", "rubrik", "titel")
        if not any(marker in lowered for marker in title_markers):
            return False

        return (
            self.extract_requested_document_type(query) is not None
            or self.is_document_reference_query(query)
            or any(
                marker in lowered
                for marker in (
                    "document",
                    "documents",
                    "file",
                    "files",
                    "dokument",
                    "fil",
                    "filer",
                )
            )
        )

    def summarize_document_titles(
        self,
        query: str,
        allowed_document_ids: list[str] | None = None,
        history: list | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        if not self.is_document_title_query(query):
            return None

        resolved_document_ids = self.find_referenced_documents(
            query,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if not resolved_document_ids:
            resolved_document_ids = self.resolve_follow_up_document_ids(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )

        documents: list[DocumentRecord] = []
        if resolved_document_ids:
            for document_id in resolved_document_ids:
                document = self.get_document_for_viewer(
                    document_id,
                    is_admin=is_admin,
                    viewer_username=viewer_username,
                )
                if document:
                    documents.append(document)
        else:
            documents = self.find_documents_by_metadata(
                query,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )

        if not documents:
            return None

        title_rows = [
            (document.original_name, document.document_title)
            for document in documents[:4]
            if document.document_title
        ]
        if not title_rows:
            return None

        if len(title_rows) == 1:
            document_name, title = title_rows[0]
            return f"The title in {document_name} is {title}."

        requested_type = self.extract_requested_document_type(query)
        type_label = (
            self._format_document_type_label(requested_type)
            if requested_type
            else "documents"
        )
        title_list = "; ".join(
            f"{document_name}: {title}" for document_name, title in title_rows
        )
        extra_count = max(0, len(documents) - len(title_rows))
        suffix = (
            f" I found {extra_count} more matching documents without detected titles."
            if extra_count
            else ""
        )
        return (
            f"I found {len(title_rows)} matching {type_label} with detected titles: "
            f"{title_list}.{suffix}"
        )

    def summarize_document_entities_by_metadata(
        self,
        query: str,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        requested_type = self.extract_requested_document_type(query)
        requested_year = self.extract_requested_document_year(query)
        if not requested_type:
            return None

        inventory_query = f"list {requested_type}"
        if requested_year:
            inventory_query = f"{inventory_query} from {requested_year}"

        matching_documents = self.find_documents_by_metadata(
            inventory_query,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if not matching_documents:
            type_label = self._format_document_type_label(requested_type)
            year_suffix = f" from {requested_year}" if requested_year else ""
            return f"I could not find any {type_label}{year_suffix} among your uploaded documents."

        entity_scores: dict[str, float] = {}
        entity_labels: dict[str, str] = {}
        entity_documents: dict[str, set[str]] = {}

        for document in matching_documents:
            signal_scores = {
                self._normalize_entity_text(signal.value): float(signal.score)
                for signal in document.document_signals
                if signal.category == "entity"
            }
            for entity in document.document_entities:
                normalized = self._normalize_entity_text(entity)
                if not normalized:
                    continue
                score = signal_scores.get(normalized, 0.6)
                if score > entity_scores.get(normalized, 0.0):
                    entity_scores[normalized] = score
                    entity_labels[normalized] = entity
                entity_documents.setdefault(normalized, set()).add(document.original_name)

        if not entity_scores:
            type_label = self._format_document_type_label(requested_type)
            return f"I found {len(matching_documents)} {type_label}, but I could not confidently identify company names in them yet."

        ranked_entities = sorted(
            entity_scores.items(),
            key=lambda item: (item[1], len(entity_documents.get(item[0], set()))),
            reverse=True,
        )[:4]
        type_label = self._format_document_type_label(requested_type)
        year_suffix = f" from {requested_year}" if requested_year else ""

        if len(ranked_entities) == 1:
            normalized, _ = ranked_entities[0]
            entity = entity_labels[normalized]
            document_list = ", ".join(sorted(entity_documents.get(normalized, set())))
            return (
                f"The {type_label}{year_suffix} mention {entity}. "
                f"I found it in {document_list}."
            )

        entity_names = [entity_labels[normalized] for normalized, _ in ranked_entities]
        leading_names = ", ".join(entity_names[:-1])
        return (
            f"The {type_label}{year_suffix} mention these company names: "
            f"{leading_names}, and {entity_names[-1]}."
        )

    def summarize_largest_document(
        self,
        *,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        documents = self.list_uploaded_documents(
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if not documents:
            return None

        largest_document = max(
            documents,
            key=lambda item: (item.size_bytes, item.uploaded_at or ""),
        )
        return (
            f"The largest uploaded document is {largest_document.original_name} at "
            f"{self._format_size_bytes(largest_document.size_bytes)}."
        )

    def summarize_document_upload_time(
        self,
        query: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        document = self.resolve_primary_document(
            query,
            history=history,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if document is None:
            documents = self.list_uploaded_documents(
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if not documents:
                return None
            document = documents[0]

        return (
            f"{document.original_name} was uploaded at "
            f"{self._format_uploaded_at(document.uploaded_at)}."
        )

    def summarize_signed_documents(
        self,
        *,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        documents = self.list_uploaded_documents(
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if not documents:
            return None

        candidates = [
            document
            for document in documents
            if self._document_has_signature_markers(document)
        ]
        if not candidates:
            return (
                "I did not find clear signature markers in your uploaded documents, "
                "so I cannot confidently confirm any signed documents yet."
            )

        leading_names = ", ".join(document.original_name for document in candidates[:4])
        if len(candidates) == 1:
            return (
                f"I found one document with signature-related markers: {leading_names}. "
                "That suggests it may be signed, but I cannot confirm a completed signature from text alone."
            )

        if len(candidates) <= 4:
            return (
                f"I found {len(candidates)} documents with signature-related markers: {leading_names}. "
                "That suggests they may be signed, but I cannot confirm completed signatures from text alone."
            )

        return (
            f"I found {len(candidates)} documents with signature-related markers. "
            f"The first few are {leading_names}, and {len(candidates) - 4} more. "
            "That suggests some may be signed, but I cannot confirm completed signatures from text alone."
        )

    def summarize_document_kind_confirmation(
        self,
        query: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        requested_type = self.extract_requested_document_type(query)
        if not requested_type:
            return None

        document = self.resolve_primary_document(
            query,
            history=history,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if document is None:
            return None

        detected_type = document.detected_document_type or "document"
        if self._document_matches_requested_type(document, requested_type):
            return (
                f"Yes, {document.original_name} is {self._with_indefinite_article(requested_type)}."
            )

        return (
            f"No, {document.original_name} looks more like "
            f"{self._with_indefinite_article(detected_type)}."
        )

    def summarize_document_companies(
        self,
        query: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        document = self.resolve_primary_document(
            query,
            history=history,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if document is None:
            return None

        companies = self._document_company_candidates(document)
        if not companies:
            return (
                f"I could not identify clear company names in {document.original_name} yet."
            )

        return (
            f"The clearest company names in {document.original_name} are "
            f"{self._join_phrases(companies[:2])}."
        )

    def summarize_document_products(
        self,
        query: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        requested_type = self.extract_requested_document_type(query)
        if requested_type and self.is_multi_document_product_query(query):
            matching_documents = self.find_documents_by_metadata(
                query,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if matching_documents:
                lowered = " ".join(query.lower().split())
                if "other " in lowered:
                    primary_document = self.resolve_primary_document(
                        query,
                        history=history,
                        allowed_document_ids=allowed_document_ids,
                        is_admin=is_admin,
                        viewer_username=viewer_username,
                    )
                    if primary_document is not None:
                        filtered_documents = [
                            document
                            for document in matching_documents
                            if document.id != primary_document.id
                        ]
                        if filtered_documents:
                            matching_documents = filtered_documents
                return self._summarize_products_for_documents(matching_documents)

        document = self.resolve_primary_document(
            query,
            history=history,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if document is not None:
            return self._summarize_products_for_documents([document])

        if requested_type:
            matching_documents = self.find_documents_by_metadata(
                query,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if matching_documents:
                return self._summarize_products_for_documents(matching_documents)

        return None

    def summarize_document_invoice_facts(
        self,
        query: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        document = self.resolve_primary_document(
            query,
            history=history,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if document is None:
            matching_documents = self.find_documents_by_metadata(
                query,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            document = matching_documents[0] if matching_documents else None
        if document is None:
            return None

        summary = self._coerce_commercial_summary(document.commercial_summary)
        if not summary:
            return None

        details: list[str] = []
        if summary.invoice_number:
            details.append(f"invoice number {summary.invoice_number}")
        if summary.invoice_date:
            details.append(f"invoice date {summary.invoice_date}")
        if summary.due_date:
            details.append(f"due date {summary.due_date}")
        if summary.subtotal is not None:
            details.append(
                "subtotal "
                + self._format_commercial_money(summary.subtotal, summary.currency)
            )
        if summary.tax is not None:
            details.append(
                "tax "
                + self._format_commercial_money(summary.tax, summary.currency)
            )
        if summary.total is not None:
            details.append(
                "total "
                + self._format_commercial_money(summary.total, summary.currency)
            )
        if not details:
            return None

        product_names = [
            item.description
            for item in summary.line_items[:4]
            if item.description
        ]
        product_suffix = (
            f" Extracted items include {self._join_phrases(product_names)}."
            if product_names
            else ""
        )
        return (
            f"The invoice details in {document.original_name} are: "
            f"{'; '.join(details)}.{product_suffix}"
        )

    def summarize_document_code_functions(
        self,
        query: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        document = self.resolve_primary_document(
            query,
            history=history,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if document is None:
            return None

        functions = self._extract_code_function_names(document)
        if not functions:
            return f"I could not find clear function declarations in {document.original_name}."

        return (
            f"The function names in {document.original_name} include "
            f"{self._join_phrases(functions[:5])}."
        )

    def summarize_document_risks(
        self,
        query: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        return self._summarize_document_findings(
            query=query,
            category="risk",
            history=history,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )

    def summarize_document_actions(
        self,
        query: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        return self._summarize_document_findings(
            query=query,
            category="action",
            history=history,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )

    def summarize_document_decisions(
        self,
        query: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        return self._summarize_document_findings(
            query=query,
            category="decision",
            history=history,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )

    def summarize_document_deadlines(
        self,
        query: str,
        *,
        history: list[ChatHistoryMessage] | None = None,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        return self._summarize_document_findings(
            query=query,
            category="deadline",
            history=history,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )

    def summarize_similar_documents(
        self,
        query: str | None = None,
        history: list[ChatHistoryMessage] | None = None,
        minimum_score: float = 0.22,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        processed_documents = [
            document
            for document in self._filter_documents_for_viewer(
                self.list_documents(),
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if document.processing_status == "processed"
        ]
        if len(processed_documents) < 2:
            return None

        if query and self.is_broad_similarity_inventory_query(query):
            family_summary = self._summarize_duplicate_document_families(
                processed_documents
            )
            if family_summary:
                return family_summary
            target_document_ids: list[str] = []
        else:
            target_document_ids = self._resolve_similarity_target_document_ids(
                query=query,
                history=history or [],
                processed_documents=processed_documents,
            )
        if target_document_ids:
            target_documents = [
                document
                for document in processed_documents
                if document.id in target_document_ids
            ]
            if target_documents:
                return self._summarize_documents_similar_to_target(
                    processed_documents=processed_documents,
                    target_documents=target_documents,
                    query=query,
                    minimum_score=minimum_score,
                )

        candidates: list[tuple[float, str, str]] = []
        document_terms = {
            document.id: self._document_term_set(document.id)
            for document in processed_documents
        }

        for index, left_document in enumerate(processed_documents):
            for right_document in processed_documents[index + 1 :]:
                left_terms = document_terms[left_document.id]
                right_terms = document_terms[right_document.id]
                text_score = self._jaccard_similarity(left_terms, right_terms)
                title_score = SequenceMatcher(
                    None,
                    left_document.original_name.lower(),
                    right_document.original_name.lower(),
                ).ratio()
                combined_score = (text_score * 0.85) + (title_score * 0.15)
                if combined_score < minimum_score:
                    continue

                candidates.append(
                    (
                        combined_score,
                        left_document.original_name,
                        right_document.original_name,
                    )
                )

        if not candidates:
            return "I did not find any uploaded documents that look strongly similar."

        candidates.sort(key=lambda item: item[0], reverse=True)
        top_candidates = candidates[:3]
        strongest_score, strongest_left, strongest_right = top_candidates[0]

        if len(top_candidates) == 1:
            return (
                f"The two most similar uploaded documents are {strongest_left} and"
                f" {strongest_right}, with about {round(strongest_score * 100)}%"
                " overlap in their extracted content."
            )

        additional_pairs = ", ".join(
            f"{left_name} and {right_name}"
            for _, left_name, right_name in top_candidates[1:]
        )
        return (
            f"The closest match is {strongest_left} and {strongest_right}, with about"
            f" {round(strongest_score * 100)}% overlap in their extracted content."
            f" Other similar pairs include {additional_pairs}."
        )

    def summarize_document_versions(
        self,
        query: str | None = None,
        history: list[ChatHistoryMessage] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        processed_documents = [
            document
            for document in self._filter_documents_for_viewer(
                self.list_documents(),
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if document.processing_status == "processed"
        ]
        if not processed_documents:
            return None

        target_documents = self._resolve_comparison_documents(
            query=query,
            history=history or [],
            processed_documents=processed_documents,
        )
        if not target_documents:
            return None

        family_documents = self._family_documents_for_targets(
            target_documents,
            processed_documents,
        )
        if len(family_documents) < 2:
            return (
                f"I found {target_documents[0].original_name}, but there is only one"
                " document in that family right now, so I cannot compare versions yet."
            )

        latest_document = family_documents[0]
        previous_document = family_documents[1]
        response = (
            f"The latest document in the {latest_document.document_family_label or 'document'} family"
            f" is {latest_document.original_name}"
        )
        if latest_document.document_date:
            response += f" dated {latest_document.document_date}"
        if latest_document.document_version_label:
            response += f" ({latest_document.document_version_label})"
        response += "."
        response += f" The previous version is {previous_document.original_name}"
        if previous_document.document_date:
            response += f" dated {previous_document.document_date}"
        if previous_document.document_version_label:
            response += f" ({previous_document.document_version_label})"
        response += "."
        return response

    def summarize_document_changes(
        self,
        query: str | None = None,
        history: list[ChatHistoryMessage] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        processed_documents = [
            document
            for document in self._filter_documents_for_viewer(
                self.list_documents(),
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if document.processing_status == "processed"
        ]
        if len(processed_documents) < 2:
            return None

        target_documents = self._resolve_comparison_documents(
            query=query,
            history=history or [],
            processed_documents=processed_documents,
        )
        if not target_documents:
            return None

        if len(target_documents) >= 2:
            left_document, right_document = target_documents[:2]
        else:
            family_documents = self._family_documents_for_targets(
                target_documents,
                processed_documents,
            )
            if len(family_documents) < 2:
                return (
                    f"I found {target_documents[0].original_name}, but I need at least two"
                    " related documents before I can summarize changes."
                )
            left_document, right_document = family_documents[:2]

        return self._summarize_document_delta(
            left_document,
            right_document,
            query=query,
            conflict_mode=self.is_document_conflict_query(query or ""),
        )

    def _resolve_comparison_documents(
        self,
        *,
        query: str | None,
        history: list[ChatHistoryMessage],
        processed_documents: list[DocumentRecord],
    ) -> list[DocumentRecord]:
        resolved_ids: list[str] = []
        if query:
            resolved_ids = self.find_referenced_documents(query)[:2]

        if not resolved_ids and history:
            resolved_ids = self._resolve_similarity_target_document_ids(
                query=query,
                history=history,
                processed_documents=processed_documents,
            )[:2]

        resolved_documents = [
            document
            for document in processed_documents
            if document.id in resolved_ids
        ]
        if resolved_documents:
            resolved_documents.sort(
                key=lambda item: resolved_ids.index(item.id)
                if item.id in resolved_ids
                else len(resolved_ids)
            )
            return resolved_documents[:2]

        requested_type = self.extract_requested_document_type(query or "")
        if requested_type:
            matching_documents = [
                document
                for document in processed_documents
                if self._document_matches_requested_type(document, requested_type)
            ]
            if matching_documents:
                matching_documents.sort(
                    key=self._document_version_sort_key,
                    reverse=True,
                )
                return matching_documents[:2]

        return []

    def _family_documents_for_targets(
        self,
        target_documents: list[DocumentRecord],
        processed_documents: list[DocumentRecord],
    ) -> list[DocumentRecord]:
        if not target_documents:
            return []

        family_key = target_documents[0].document_family_key
        if not family_key:
            return target_documents[:1]

        family_documents = [
            document
            for document in processed_documents
            if document.document_family_key == family_key
        ]
        family_documents.sort(key=self._document_version_sort_key, reverse=True)
        return family_documents

    def _summarize_document_delta(
        self,
        left_document: DocumentRecord,
        right_document: DocumentRecord,
        *,
        query: str | None,
        conflict_mode: bool,
    ) -> str:
        shared_terms = self._shared_document_theme_terms(left_document, right_document)
        left_only_topics = [
            topic
            for topic in left_document.document_topics
            if topic not in right_document.document_topics
        ][:3]
        right_only_topics = [
            topic
            for topic in right_document.document_topics
            if topic not in left_document.document_topics
        ][:3]
        lead = (
            f"I compared {left_document.original_name} and {right_document.original_name}."
        )
        date_detail_parts: list[str] = []
        if left_document.document_date:
            date_detail_parts.append(
                f"{left_document.original_name} is dated {left_document.document_date}"
            )
        if right_document.document_date:
            date_detail_parts.append(
                f"{right_document.original_name} is dated {right_document.document_date}"
            )
        date_detail = ""
        if date_detail_parts:
            date_detail = " " + ". ".join(date_detail_parts) + "."

        overlap_detail = ""
        if shared_terms:
            overlap_detail = (
                " They still overlap around " + ", ".join(shared_terms[:3]) + "."
            )

        focus_evidence = self._compare_document_focus_evidence(
            left_document,
            right_document,
            query=query,
        )
        if focus_evidence:
            return lead + date_detail + " " + focus_evidence

        if not left_only_topics and not right_only_topics:
            if conflict_mode:
                return (
                    lead
                    + date_detail
                    + overlap_detail
                    + " I do not see a clear contradiction from the metadata, but they should still be reviewed side by side if wording precision matters."
                )
            return (
                lead
                + date_detail
                + overlap_detail
                + " Their metadata looks closely aligned, so any change is more likely to be wording or detail level than subject matter."
            )

        left_topic_line = ""
        if left_only_topics:
            left_topic_line = (
                f" {left_document.original_name} leans more toward "
                + ", ".join(left_only_topics)
                + "."
            )
        right_topic_line = ""
        if right_only_topics:
            right_topic_line = (
                f" {right_document.original_name} adds or emphasizes "
                + ", ".join(right_only_topics)
                + "."
            )

        if conflict_mode:
            return (
                lead
                + date_detail
                + overlap_detail
                + left_topic_line
                + right_topic_line
                + " This looks more like a version or emphasis shift than a hard contradiction, but it is still a good pair to review together."
            )

        return lead + date_detail + overlap_detail + left_topic_line + right_topic_line

    def _compare_document_focus_evidence(
        self,
        left_document: DocumentRecord,
        right_document: DocumentRecord,
        *,
        query: str | None,
    ) -> str | None:
        if not query:
            return None

        left_evidence = self._extract_query_evidence(left_document, query)
        right_evidence = self._extract_query_evidence(right_document, query)
        if not left_evidence or not right_evidence:
            return None

        focus_label = self._focus_label_from_query(query) or "the requested detail"
        left_value = self._extract_primary_evidence_value(left_evidence)
        right_value = self._extract_primary_evidence_value(right_evidence)
        if left_value and right_value:
            if left_value == right_value:
                return (
                    f"Both documents show {focus_label} {left_value}, so I do not see a disagreement."
                )
            return (
                f"{left_document.original_name} shows {focus_label} {left_value}, while "
                f"{right_document.original_name} shows {focus_label} {right_value}. "
                "That suggests a real difference."
            )

        if left_evidence == right_evidence:
            return (
                f"Both documents point to the same result for {focus_label}: {left_evidence}."
            )

        return (
            f"{left_document.original_name} points to {left_evidence}, while "
            f"{right_document.original_name} points to {right_evidence}."
        )

    def _extract_query_evidence(
        self,
        document: DocumentRecord,
        query: str,
        *,
        window: int = 90,
    ) -> str | None:
        extracted_path = self.extracted_text_dir / f"{document.id}.txt"
        if not extracted_path.exists():
            return None

        content = self._normalize_text_fragment(
            extracted_path.read_text(encoding="utf-8")
        )
        normalized_content = " ".join(content.split())
        if not normalized_content:
            return None

        focus_terms = [
            term
            for term in (self.extract_focus_terms(query) or self.extract_query_terms(query))
            if term not in {"document", "documents", "file", "files", "disagree", "compare", "difference"}
        ]
        if not focus_terms:
            return None

        matched_phrase = ""
        focus_phrase = " ".join(focus_terms[:2]).strip()
        lowered_content = normalized_content.lower()
        start_index = -1
        if focus_phrase and focus_phrase in lowered_content:
            matched_phrase = focus_phrase
            start_index = lowered_content.find(focus_phrase)
        else:
            for term in focus_terms:
                start_index = lowered_content.find(term.lower())
                if start_index >= 0:
                    matched_phrase = term
                    break

        if start_index < 0:
            return None

        snippet_start = max(0, start_index - 18)
        snippet_end = min(len(normalized_content), start_index + len(matched_phrase) + window)
        snippet = normalized_content[snippet_start:snippet_end].strip(" ,;:-")
        if snippet_start > 0 and " " in snippet:
            snippet = snippet.split(" ", 1)[-1]
        if snippet_end < len(normalized_content) and " " in snippet:
            snippet = snippet.rsplit(" ", 1)[0]
        snippet = re.sub(r"\s+", " ", snippet).strip(" ,;:-")
        return snippet or None

    def _focus_label_from_query(self, query: str) -> str | None:
        lowered = " ".join(query.lower().split())
        patterns = (
            r"\babout\s+the\s+([a-z0-9 /_-]+)",
            r"\bfor\s+the\s+([a-z0-9 /_-]+)",
            r"\bthe\s+([a-z0-9 /_-]+?)\s*(?:\?|$)",
        )
        for pattern in patterns:
            match = re.search(pattern, lowered)
            if not match:
                continue
            candidate = match.group(1).strip(" ?!.,:;")
            candidate = re.sub(
                r"\b(?:documents?|files?|spreadsheet|spreadsheets|policy|policies)\b",
                "",
                candidate,
            )
            candidate = " ".join(candidate.split())
            if candidate:
                return candidate
        focus_terms = self.extract_focus_terms(query)
        if focus_terms:
            return " ".join(focus_terms[:2])
        return None

    def _extract_primary_evidence_value(self, evidence: str) -> str | None:
        q_match = re.search(
            r"\bq[1-4]\b[^.]{0,40}?\btotal\b[^0-9]{0,12}(\d+(?:[.,]\d+)?)",
            evidence,
            flags=re.IGNORECASE,
        )
        if q_match:
            return q_match.group(1)

        number_match = re.search(r"\b\d+(?:[.,]\d+)?\b", evidence)
        if number_match:
            return number_match.group(0)
        return None

    def _document_version_sort_key(self, document: DocumentRecord) -> tuple[str, int, str]:
        date_key = document.document_date or ""
        version_key = document.document_version_number or 0
        upload_key = document.uploaded_at or ""
        return (date_key, version_key, upload_key)

    def _build_family_summaries(
        self,
        processed_documents: list[DocumentRecord],
    ) -> list[DocumentFamilySummary]:
        families: dict[str, list[DocumentRecord]] = {}
        for document in processed_documents:
            if not document.document_family_key:
                continue
            families.setdefault(document.document_family_key, []).append(document)

        summaries: list[DocumentFamilySummary] = []
        for family_key, family_documents in families.items():
            family_documents.sort(key=self._document_version_sort_key, reverse=True)
            latest_document = family_documents[0]
            topic_counter: Counter[str] = Counter()
            for family_document in family_documents:
                topic_counter.update(family_document.document_topics[:3])
            summaries.append(
                DocumentFamilySummary(
                    family_key=family_key,
                    family_label=latest_document.document_family_label or family_key,
                    document_count=len(family_documents),
                    latest_document_id=latest_document.id,
                    latest_document_name=latest_document.original_name,
                    latest_document_date=latest_document.document_date,
                    topics=[topic for topic, _ in topic_counter.most_common(4)],
                    members=[
                        DocumentFamilyMember(
                            document_id=document.id,
                            document_name=document.original_name,
                            document_date=document.document_date,
                            version_label=document.document_version_label,
                            uploaded_at=document.uploaded_at,
                        )
                        for document in family_documents[:4]
                    ],
                )
            )

        summaries.sort(
            key=lambda item: (
                item.document_count,
                item.latest_document_date or "",
                item.latest_document_name,
            ),
            reverse=True,
        )
        return summaries

    def _summarize_duplicate_document_families(
        self,
        processed_documents: list[DocumentRecord],
    ) -> str | None:
        family_summaries = [
            summary
            for summary in self._build_family_summaries(processed_documents)
            if summary.document_count >= 2 and len(summary.members) >= 2
        ]
        if not family_summaries:
            return None

        ranked_pairs: list[tuple[DocumentFamilySummary, str, str]] = []
        for summary in family_summaries:
            member_names = [
                member.document_name
                for member in summary.members
                if member.document_name
            ]
            if len(member_names) < 2:
                continue
            left_name = member_names[0]
            right_name = next(
                (name for name in member_names[1:] if name != left_name),
                member_names[1],
            )
            ranked_pairs.append((summary, left_name, right_name))

        if not ranked_pairs:
            return None

        strongest_summary, strongest_left, strongest_right = ranked_pairs[0]
        family_label = (
            strongest_summary.family_label
            or strongest_summary.family_key
            or "document family"
        )
        response = (
            f"The clearest repeated document family is {family_label}: "
            f"{strongest_left} and {strongest_right}."
        )
        response += (
            f" I found {strongest_summary.document_count} related uploads in that family."
        )

        additional_families = ", ".join(
            f"{summary.family_label or summary.family_key} ({summary.document_count})"
            for summary, _, _ in ranked_pairs[1:4]
            if summary.family_label or summary.family_key
        )
        if additional_families:
            response += f" Other repeated families include {additional_families}."
        return response

    def semantic_sources_match_query(
        self, query: str, sources: list[ChatSource]
    ) -> bool:
        if not sources:
            return False

        if self.is_document_reference_query(query):
            return True

        return any(self.source_matches_query(query, source) for source in sources)

    def source_matches_query(self, query: str, source: ChatSource) -> bool:
        topic_phrase = self.extract_topic_phrase(query)
        excerpt = source.excerpt.lower()
        section_title = (source.section_title or "").lower()
        searchable_text = f"{section_title}\n{excerpt}".strip()
        if topic_phrase and len(topic_phrase.split()) >= 2:
            if topic_phrase in searchable_text:
                return True

            phrase_terms = self._query_terms(topic_phrase)
            if phrase_terms:
                matched_phrase_terms = {
                    term for term in phrase_terms if term in searchable_text
                }
                required_matches = min(
                    len(phrase_terms),
                    max(2, len(phrase_terms) - 1),
                )
                if len(matched_phrase_terms) >= required_matches:
                    return True

        terms = self.extract_query_terms(query)
        if not terms:
            return False

        matched_terms = {term for term in terms if term in searchable_text}
        if not matched_terms:
            document = self.get_document(source.document_id)
            if document is not None:
                signal_score = self._document_signal_score(document, query, set(terms))
                if signal_score >= 0.55:
                    return True
            return False

        requested_document_type = self.extract_requested_document_type(query)
        if requested_document_type:
            document = self.get_document(source.document_id)
            if document is not None and self._document_matches_requested_type(
                document,
                requested_document_type,
            ):
                return len(matched_terms) >= 1

        if len(terms) >= 2:
            return len(matched_terms) >= 2

        return source.score >= max(settings.retrieval_min_score, 0.55)

    def hydrate_sources(
        self,
        query: str,
        sources: list[ChatSource],
        limit: int | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> list[ChatSource]:
        if not sources:
            return []

        query_terms = self.extract_query_terms(query)
        excerpt_terms = self.extract_focus_terms(query) or query_terms
        hydrated_sources: list[ChatSource] = []

        for source in sources:
            document = self.get_document_for_viewer(
                source.document_id,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if document is None:
                continue

            source_ocr_used = source.ocr_used or bool(document.ocr_used)

            chunks_path = self.chunks_dir / f"{source.document_id}.json"
            if not chunks_path.exists():
                source.ocr_used = source_ocr_used
                hydrated_sources.append(source)
                continue

            with chunks_path.open("r", encoding="utf-8") as file_handle:
                chunks = json.load(file_handle)

            merged_excerpt = self._build_source_excerpt(
                chunks=chunks,
                chunk_index=source.chunk_index,
                query_terms=excerpt_terms,
            )
            hydrated_sources.append(
                ChatSource(
                    document_id=source.document_id,
                    document_name=source.document_name,
                    chunk_index=source.chunk_index,
                    score=source.score,
                    excerpt=merged_excerpt,
                    section_title=source.section_title,
                    page_number=source.page_number,
                    source_kind=source.source_kind,
                    detected_document_type=source.detected_document_type or document.detected_document_type,
                    document_date=source.document_date or document.document_date,
                    document_date_label=source.document_date_label or document.document_date_label,
                    ocr_used=source_ocr_used,
                )
            )

        hydrated_sources.sort(key=lambda item: item.score, reverse=True)
        if limit is not None:
            return hydrated_sources[:limit]
        return hydrated_sources

    def _document_matches_requested_type(
        self,
        document: DocumentRecord,
        requested_type: str,
    ) -> bool:
        if requested_type in {"word", "spreadsheet", "presentation"}:
            return (document.source_kind or "document") == requested_type

        detected_type = document.detected_document_type or "document"
        if detected_type == requested_type:
            return True

        thematic_types = {"roadmap", "architecture", "features"}
        if requested_type not in thematic_types:
            return False

        alias_terms = [
            alias.lower()
            for alias in self.DOCUMENT_TYPE_ALIASES.get(requested_type, set())
            if alias
        ]
        searchable_parts = [
            document.original_name,
            document.document_title or "",
            document.source_kind or "",
            " ".join(document.document_entities[:6]),
            " ".join(signal.value for signal in document.document_signals[:8]),
        ]
        searchable_text = self._strip_accents(" ".join(searchable_parts).lower())
        return any(alias in searchable_text for alias in alias_terms)

    def _metadata_match_sort_key(
        self,
        document: DocumentRecord,
        *,
        requested_type: str | None,
        requested_entity: str | None,
    ) -> tuple[float, str]:
        score = 0.0
        detected_type = document.detected_document_type or "document"
        source_kind = (document.source_kind or "").lower()

        if requested_type and detected_type == requested_type:
            score += 5.0

        source_kind_weights = {
            "pdf": 2.6,
            "word": 2.2,
            "presentation": 1.8,
            "spreadsheet": 1.4,
            "image": 1.1,
            "markdown": 0.8,
            "text": 0.7,
            "json": 0.4,
            "xml": 0.3,
            "csv": 0.2,
            "code": 0.1,
            "config": 0.1,
        }
        score += source_kind_weights.get(source_kind, 0.5)

        if requested_type in {"invoice", "quote", "receipt"} and source_kind == "csv":
            score -= 1.4

        alias_terms = [
            self._strip_accents(alias.lower())
            for alias in self.DOCUMENT_TYPE_ALIASES.get(requested_type or "", set())
            if alias
        ]
        searchable_parts = [
            document.original_name,
            document.document_title or "",
            " ".join(document.document_topics[:4]),
            " ".join(document.document_entities[:4]),
        ]
        searchable_text = self._strip_accents(" ".join(searchable_parts).lower())
        if alias_terms and any(alias in searchable_text for alias in alias_terms):
            score += 1.4

        if requested_entity and self._document_matches_entity(document, requested_entity):
            score += 1.2

        if document.document_title:
            score += 0.4
        if document.ocr_used:
            score += 0.2
        if document.document_date:
            score += 0.2

        return (score, document.uploaded_at or "")

    def _write_metadata(self, document: DocumentRecord) -> None:
        if self._is_document_deleted(document.id):
            return

        metadata_path = self._metadata_path(document.id)
        self._write_json_atomic(metadata_path, document.model_dump())

    def _write_json_atomic(self, path: Path, payload: Any) -> None:
        temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temp_path.open("w", encoding="utf-8") as file_handle:
                json.dump(payload, file_handle, ensure_ascii=True, indent=2)
            temp_path.replace(path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _write_text_atomic(self, path: Path, text: str) -> None:
        temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            temp_path.write_text(text, encoding="utf-8")
            temp_path.replace(path)
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def _normalize_document_record(self, document: DocumentRecord) -> DocumentRecord:
        document.commercial_summary = self._coerce_commercial_summary(
            document.commercial_summary
        )
        if document.processing_status == "failed":
            document.document_signals = self._coerce_document_signals(document.document_signals)
            document.similar_documents = self._coerce_document_similarity_matches(
                document.similar_documents
            )
            document.similarity_terms = self._normalize_similarity_terms(
                document.similarity_terms
            )
            document.document_topics = self._normalize_similarity_terms(
                document.document_topics
            )[:8]
            document.processing_stage = "failed"
            return document

        if document.processing_status == "processed":
            document.document_signals = self._coerce_document_signals(document.document_signals)
            document.similar_documents = self._coerce_document_similarity_matches(
                document.similar_documents
            )
            document.similarity_terms = self._normalize_similarity_terms(
                document.similarity_terms
            )
            document.document_topics = self._normalize_similarity_terms(
                document.document_topics
            )[:8]
            if not document.processing_stage or document.processing_stage == "queued":
                document.processing_stage = "completed"
            if not document.ocr_status:
                document.ocr_status = "not_needed"
            if document.ocr_status != "used":
                document.ocr_engine = None
            self._normalize_legacy_pdf_ocr_state(document)
            return document

        if document.processing_stage == "completed":
            document.document_signals = self._coerce_document_signals(document.document_signals)
            document.similar_documents = self._coerce_document_similarity_matches(
                document.similar_documents
            )
            document.similarity_terms = self._normalize_similarity_terms(
                document.similarity_terms
            )
            document.document_topics = self._normalize_similarity_terms(
                document.document_topics
            )[:8]
            document.processing_status = "processed"
            return document

        if document.indexing_status in {"indexed", "failed", "skipped"}:
            document.document_signals = self._coerce_document_signals(document.document_signals)
            document.similar_documents = self._coerce_document_similarity_matches(
                document.similar_documents
            )
            document.similarity_terms = self._normalize_similarity_terms(
                document.similarity_terms
            )
            document.document_topics = self._normalize_similarity_terms(
                document.document_topics
            )[:8]
            document.processing_status = "processed"
            if not document.processing_stage or document.processing_stage == "queued":
                document.processing_stage = (
                    "failed" if document.indexing_status == "failed" else "completed"
                )
            if not document.ocr_status:
                document.ocr_status = "not_needed"
            if document.ocr_status != "used":
                document.ocr_engine = None
            self._normalize_legacy_pdf_ocr_state(document)
            return document

        if not document.processing_stage:
            document.processing_stage = "queued"
        if not document.ocr_status:
            document.ocr_status = "not_needed"
        if document.ocr_status != "used":
            document.ocr_engine = None
        document.document_signals = self._coerce_document_signals(document.document_signals)
        document.similar_documents = self._coerce_document_similarity_matches(
            document.similar_documents
        )
        document.similarity_terms = self._normalize_similarity_terms(
            document.similarity_terms
        )
        document.document_topics = self._normalize_similarity_terms(
            document.document_topics
        )[:8]
        self._normalize_legacy_pdf_ocr_state(document)

        return document

    def _enrich_document_metadata(self, document: DocumentRecord) -> DocumentRecord:
        extracted_path = self.extracted_text_dir / f"{document.id}.txt"
        extracted_text = ""
        if extracted_path.exists():
            extracted_text = extracted_path.read_text(encoding="utf-8")

        changed = False
        if not document.source_kind:
            document.source_kind = self.processing_service.detect_source_kind(
                document.original_name,
                document.content_type,
            )
            changed = True

        if not document.document_title and extracted_text:
            document.document_title = self.processing_service.detect_document_title(
                extracted_text,
                document.original_name,
            )
            changed = True

        if extracted_text and (
            not document.detected_document_type
            or document.detected_document_type == "document"
        ):
            detected_type = self.processing_service.detect_document_type(
                extracted_text,
                document.original_name,
                document.content_type,
            )
            if detected_type and detected_type != document.detected_document_type:
                document.detected_document_type = detected_type
                changed = True

        if extracted_text and not document.document_entities:
            document.document_entities = self.processing_service.detect_document_entities(
                extracted_text,
                document.original_name,
                document.detected_document_type,
            )
            changed = True
        elif extracted_text and self._should_refresh_entity_metadata(document):
            refreshed_entities = self.processing_service.detect_document_entities(
                extracted_text,
                document.original_name,
                document.detected_document_type,
            )
            if refreshed_entities and refreshed_entities != document.document_entities:
                document.document_entities = refreshed_entities
                changed = True

        if extracted_text and not document.document_signals:
            document.document_signals = self.processing_service.detect_document_signals(
                extracted_text,
                document.original_name,
                document.detected_document_type,
                document.document_title,
                document.document_entities,
            )
            document.document_signals = self._coerce_document_signals(document.document_signals)
            changed = True
        elif extracted_text and self._should_refresh_entity_metadata(document):
            refreshed_signals = self.processing_service.detect_document_signals(
                extracted_text,
                document.original_name,
                document.detected_document_type,
                document.document_title,
                document.document_entities,
            )
            refreshed_signals = self._coerce_document_signals(refreshed_signals)
            if refreshed_signals and refreshed_signals != document.document_signals:
                document.document_signals = refreshed_signals
                changed = True

        if (
            not document.document_date
            or not document.document_date_label
            or not document.document_date_kind
        ):
            (
                detected_date,
                detected_date_label,
                detected_date_kind,
            ) = self.processing_service.detect_document_date(
                extracted_text,
                document.original_name,
                document.detected_document_type,
            )
            if detected_date and not document.document_date:
                document.document_date = detected_date
                changed = True
            if detected_date_label and not document.document_date_label:
                document.document_date_label = detected_date_label
                changed = True
            if detected_date_kind and not document.document_date_kind:
                document.document_date_kind = detected_date_kind
                changed = True

        if extracted_text and self._should_refresh_commercial_summary(document):
            commercial_summary = self.processing_service.extract_commercial_summary(
                extracted_text,
                document.original_name,
                document.detected_document_type,
            )
            if commercial_summary != document.commercial_summary:
                document.commercial_summary = commercial_summary
                changed = True

        if extracted_text:
            family_key = self._derive_document_family_key(document)
            family_label = self._derive_document_family_label(document)
            version_label, version_number = self._derive_document_version(document)
            topics = self._build_document_topics(document, extracted_text=extracted_text)
            summary_anchor = self._derive_document_summary_anchor(
                document,
                extracted_text=extracted_text,
            )
            if family_key != document.document_family_key:
                document.document_family_key = family_key
                changed = True
            if family_label != document.document_family_label:
                document.document_family_label = family_label
                changed = True
            if version_label != document.document_version_label:
                document.document_version_label = version_label
                changed = True
            if version_number != document.document_version_number:
                document.document_version_number = version_number
                changed = True
            if topics != self._normalize_similarity_terms(document.document_topics):
                document.document_topics = topics
                changed = True
            if summary_anchor != document.document_summary_anchor:
                document.document_summary_anchor = summary_anchor
                changed = True

            similarity_profile = self._build_document_similarity_profile(
                document,
                sample_text=extracted_text,
            )
            similarity_terms = self._build_similarity_terms(
                document,
                extracted_text=extracted_text,
            )
            normalized_similarity_terms = self._normalize_similarity_terms(similarity_terms)
            if similarity_profile != document.similarity_profile:
                document.similarity_profile = similarity_profile
                changed = True
            if normalized_similarity_terms != self._normalize_similarity_terms(
                document.similarity_terms
            ):
                document.similarity_terms = normalized_similarity_terms
                changed = True
            if document.similarity_profile and document.similarity_updated_at is None:
                document.similarity_updated_at = datetime.now(UTC).isoformat()
                changed = True

        if changed:
            self._write_metadata(document)

        return document

    def _normalize_legacy_pdf_ocr_state(self, document: DocumentRecord) -> None:
        is_pdf = (
            document.content_type == "application/pdf"
            or document.original_name.lower().endswith(".pdf")
        )
        if not is_pdf:
            return

        if (
            document.character_count == 0
            and document.indexing_status == "skipped"
            and document.ocr_status == "not_needed"
        ):
            document.ocr_status = "unavailable"
            if not document.ocr_error:
                document.ocr_error = (
                    "This PDF does not contain extractable text. Reprocess it after OCR is available."
                )

    def _compact_document_record(self, document: DocumentRecord) -> DocumentRecord:
        document.document_entities = document.document_entities[:2]
        document.document_signals = sorted(
            self._coerce_document_signals(document.document_signals),
            key=lambda item: item.score,
            reverse=True,
        )[:3]
        document.document_topics = self._normalize_similarity_terms(
            document.document_topics
        )[:4]
        document.similar_documents = self._coerce_document_similarity_matches(
            document.similar_documents
        )[:2]
        document.similarity_terms = self._normalize_similarity_terms(
            document.similarity_terms
        )[:8]
        return document

    def _coerce_document_signals(
        self,
        values: list[DocumentSignal | dict[str, object]] | None,
    ) -> list[DocumentSignal]:
        if not values:
            return []

        coerced: list[DocumentSignal] = []
        for value in values:
            if isinstance(value, DocumentSignal):
                coerced.append(value)
                continue

            try:
                coerced.append(DocumentSignal.model_validate(value))
            except Exception:
                continue

        return coerced

    def _coerce_commercial_summary(
        self,
        value: DocumentCommercialSummary | dict[str, object] | None,
    ) -> DocumentCommercialSummary | None:
        if value is None:
            return None
        try:
            summary = (
                value
                if isinstance(value, DocumentCommercialSummary)
                else DocumentCommercialSummary.model_validate(value)
            )
        except Exception:
            return None

        line_items: list[DocumentCommercialLineItem] = []
        for item in summary.line_items:
            try:
                line_item = (
                    item
                    if isinstance(item, DocumentCommercialLineItem)
                    else DocumentCommercialLineItem.model_validate(item)
                )
            except Exception:
                continue
            if line_item.description.strip():
                line_items.append(line_item)

        summary.line_items = line_items[:30]
        if not any(
            (
                summary.invoice_number,
                summary.invoice_date,
                summary.due_date,
                summary.subtotal is not None,
                summary.tax is not None,
                summary.total is not None,
                summary.line_items,
            )
        ):
            return None
        return summary

    def _coerce_document_similarity_matches(
        self,
        values: list[DocumentSimilarityMatch | dict[str, object]] | None,
    ) -> list[DocumentSimilarityMatch]:
        if not values:
            return []

        coerced: list[DocumentSimilarityMatch] = []
        seen_ids: set[str] = set()
        for value in values:
            if isinstance(value, DocumentSimilarityMatch):
                match = value
            else:
                try:
                    match = DocumentSimilarityMatch.model_validate(value)
                except Exception:
                    continue

            if not match.document_id or match.document_id in seen_ids:
                continue
            seen_ids.add(match.document_id)
            coerced.append(
                DocumentSimilarityMatch(
                    document_id=match.document_id,
                    document_name=match.document_name,
                    score=round(max(0.0, min(float(match.score), 1.0)), 4),
                    shared_terms=self._normalize_similarity_terms(match.shared_terms)[:4],
                    reason=self._normalize_optional_text(match.reason),
                )
            )

        return sorted(coerced, key=lambda item: item.score, reverse=True)

    def _normalize_similarity_terms(self, values: list[str] | None) -> list[str]:
        if not values:
            return []

        normalized: list[str] = []
        seen_terms: set[str] = set()
        for value in values:
            term = self._strip_accents(str(value).lower()).strip()
            term = re.sub(r"[^a-z0-9-]+", " ", term)
            term = " ".join(term.split())
            if len(term) < 3 or term in seen_terms:
                continue
            seen_terms.add(term)
            normalized.append(term)
        return normalized[:40]

    def _should_refresh_entity_metadata(self, document: DocumentRecord) -> bool:
        if not settings.gliner_backfill_existing:
            return False
        if not settings.gliner_enabled:
            return False
        if document.processing_status != "processed":
            return False
        if document.detected_document_type not in {"invoice", "contract", "policy", "quote", "insurance", "document"}:
            return False

        strong_entity_signals = [
            signal
            for signal in self._coerce_document_signals(document.document_signals)
            if signal.category == "entity" and float(signal.score) >= 0.9
        ]
        multiword_entities = [entity for entity in document.document_entities if len(entity.split()) >= 2]
        return len(strong_entity_signals) < 2 or len(multiword_entities) < 2

    def _should_refresh_commercial_summary(self, document: DocumentRecord) -> bool:
        summary = self._coerce_commercial_summary(document.commercial_summary)
        if summary is None:
            return True
        if document.detected_document_type not in {"invoice", "receipt", "quote"}:
            return False
        if not summary.line_items:
            return True
        # Commercial extraction is deterministic and cheap compared with OCR/LLM
        # work. Re-running it keeps older invoice metadata aligned with parser
        # improvements without requiring users to re-upload documents.
        return True

    def _needs_background_intelligence_refresh(self, document: DocumentRecord) -> bool:
        if document.processing_status != "processed":
            return False
        if not document.document_family_key:
            return True
        if not document.document_family_label:
            return True
        if not document.document_topics:
            return True
        if not document.similarity_profile:
            return True
        if not document.similarity_terms:
            return True
        if document.similarity_updated_at is None:
            return True
        return False

    def _update_processing_stage(
        self,
        document: DocumentRecord,
        stage: str,
        reset_started_at: bool = False,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        if reset_started_at or document.processing_started_at is None:
            document.processing_started_at = now

        document.processing_status = "pending"
        document.processing_stage = stage
        document.processing_updated_at = now
        document.processing_error = None
        document.indexing_status = "pending"
        document.indexed_at = None
        document.indexing_error = None
        self._write_metadata(document)

    def _write_extracted_text(self, document_id: str, text: str) -> None:
        path = self.extracted_text_dir / f"{document_id}.txt"
        self._write_text_atomic(path, text)

    def _write_chunks(
        self, document_id: str, chunks: list[dict[str, str | int]]
    ) -> None:
        path = self.chunks_dir / f"{document_id}.json"
        self._write_json_atomic(path, chunks)

    def _remove_processing_artifacts(self, document_id: str) -> None:
        extracted_path = self.extracted_text_dir / f"{document_id}.txt"
        chunks_path = self.chunks_dir / f"{document_id}.json"

        if extracted_path.exists():
            extracted_path.unlink()

        if chunks_path.exists():
            chunks_path.unlink()

    def _metadata_path(self, document_id: str) -> Path:
        return self.metadata_dir / f"{document_id}.json"

    def _deletion_marker_path(self, document_id: str) -> Path:
        return self.deleted_metadata_dir / f"{document_id}.deleted"

    def _mark_document_deleted(self, document_id: str) -> None:
        self.deleted_metadata_dir.mkdir(parents=True, exist_ok=True)
        marker_path = self._deletion_marker_path(document_id)
        marker_path.write_text(datetime.now(UTC).isoformat(), encoding="utf-8")

    def _is_document_deleted(self, document_id: str) -> bool:
        return self._deletion_marker_path(document_id).exists()

    def _store_document_file(
        self,
        *,
        source_file,
        original_name: str,
        content_type: str,
        source_origin: str,
        source_connector_id: str | None = None,
        source_provider: str | None = None,
        source_uri: str | None = None,
        source_container: str | None = None,
        source_last_modified_at: str | None = None,
        visibility: str = "standard",
        access_usernames: list[str] | None = None,
    ) -> DocumentRecord:
        normalized_visibility = self._normalize_document_visibility(visibility)
        document_id = uuid4().hex
        resolved_name = Path(original_name).name
        self._validate_upload_name(resolved_name)
        safe_name = self._safe_name(resolved_name)
        stored_name = f"{document_id}_{safe_name}"
        target_path = self.uploads_dir / stored_name

        size_bytes = 0
        try:
            size_bytes = self._write_stream_with_size_limit(
                source_file=source_file,
                target_path=target_path,
            )
        except Exception:
            if target_path.exists():
                target_path.unlink()
            raise

        document = DocumentRecord(
            id=document_id,
            original_name=resolved_name,
            stored_name=stored_name,
            content_type=content_type,
            size_bytes=size_bytes,
            uploaded_at=datetime.now(UTC).isoformat(),
            source_origin=source_origin,
            source_connector_id=source_connector_id,
            source_provider=source_provider,
            source_uri=source_uri,
            source_container=source_container,
            source_last_modified_at=source_last_modified_at,
            visibility=normalized_visibility,
            access_usernames=self._normalize_document_access_usernames(
                access_usernames or [],
                visibility=normalized_visibility,
            ),
        )

        self._write_metadata(document)
        return document

    def _replace_document_file(
        self,
        *,
        document: DocumentRecord,
        source_path: Path,
        original_name: str,
        content_type: str,
        source_connector_id: str | None,
        source_provider: str | None,
        source_uri: str | None,
        source_container: str | None,
        source_last_modified_at: str | None,
        visibility: str = "standard",
        access_usernames: list[str] | None = None,
    ) -> DocumentRecord:
        normalized_visibility = self._normalize_document_visibility(visibility)
        target_path = self.uploads_dir / document.stored_name
        self._validate_upload_name(Path(original_name).name)
        with source_path.open("rb") as source_file:
            size_bytes = self._write_stream_with_size_limit(
                source_file=source_file,
                target_path=target_path,
            )

        document.original_name = Path(original_name).name
        document.content_type = content_type
        document.size_bytes = size_bytes
        document.source_origin = "connector" if source_provider or source_uri else "import"
        document.source_connector_id = source_connector_id
        document.source_provider = source_provider
        document.source_uri = source_uri
        document.source_container = source_container
        document.source_last_modified_at = source_last_modified_at
        document.visibility = normalized_visibility
        document.access_usernames = self._normalize_document_access_usernames(
            access_usernames or [],
            visibility=normalized_visibility,
        )
        document.processing_status = "pending"
        document.processing_stage = "queued"
        document.processing_started_at = None
        document.processing_updated_at = None
        document.processing_error = None
        document.indexing_status = "pending"
        document.indexed_at = None
        document.indexing_error = None
        self._write_metadata(document)
        return document

    def _guess_content_type(self, file_path: Path) -> str:
        guessed, _ = mimetypes.guess_type(str(file_path))
        return guessed or "application/octet-stream"

    def _document_is_visible_to_viewer(
        self,
        document: DocumentRecord,
        *,
        is_admin: bool,
        viewer_username: str | None = None,
    ) -> bool:
        if is_admin:
            return True
        visibility = (document.visibility or "standard").strip().lower()
        if visibility == "hidden":
            return False
        if visibility != "restricted":
            return True
        if not viewer_username:
            return False

        normalized_username = viewer_username.strip().lower()
        return normalized_username in {
            username.strip().lower()
            for username in (document.access_usernames or [])
            if username.strip()
        }

    def _normalize_document_visibility(self, visibility: str | None) -> str:
        normalized_visibility = (visibility or "standard").strip().lower()
        if normalized_visibility not in {"standard", "hidden", "restricted"}:
            raise ValueError(
                "Visibility must be 'standard', 'hidden', or 'restricted'."
            )
        return normalized_visibility

    def _filter_documents_for_viewer(
        self,
        documents: list[DocumentRecord],
        *,
        is_admin: bool,
        viewer_username: str | None = None,
    ) -> list[DocumentRecord]:
        if is_admin:
            return documents

        return [
            document
            for document in documents
            if self._document_is_visible_to_viewer(
                document,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
        ]

    def _normalize_document_access_usernames(
        self,
        values: list[str],
        *,
        visibility: str,
    ) -> list[str]:
        if visibility != "restricted":
            return []

        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            candidate = value.strip()
            if not candidate:
                continue

            user = self.user_service.get_user_by_username(candidate)
            if user is None or not user.enabled:
                raise ValueError(
                    f"User '{candidate}' does not exist or is disabled."
                )

            lowered = user.username.lower()
            if lowered in seen:
                continue

            seen.add(lowered)
            normalized.append(user.username)

        if not normalized:
            raise ValueError(
                "Restricted documents must allow at least one enabled user."
            )

        return normalized

    def _sanitize_document_for_viewer(self, document: DocumentRecord) -> DocumentRecord:
        sanitized = document.model_copy(deep=True)
        sanitized.access_usernames = []
        return sanitized

    def _safe_name(self, value: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
        return sanitized or "document"

    def _matches_document_list_filters(
        self,
        *,
        document: DocumentRecord,
        query: str,
        status_filter: str,
        type_filter: str,
        source_filter: str,
    ) -> bool:
        normalized_query = query.strip().lower()
        if normalized_query:
            haystack = " ".join(
                [
                    document.original_name,
                    document.content_type,
                    document.document_title or "",
                    document.detected_document_type or "",
                    document.document_date or "",
                    document.document_date_label or "",
                    document.processing_status,
                    document.indexing_status or "",
                    " ".join(document.document_entities or []),
                    " ".join(signal.value for signal in (document.document_signals or [])),
                ]
            ).lower()
            if normalized_query not in haystack:
                return False

        if status_filter == "processed":
            if not (
                document.processing_status == "processed"
                and document.indexing_status != "failed"
            ):
                return False
        elif status_filter == "pending":
            if document.processing_status != "pending":
                return False
        elif status_filter == "failed":
            if document.processing_status != "failed":
                return False
        elif status_filter == "index_failed":
            if document.indexing_status != "failed":
                return False

        if type_filter != "all":
            if (document.detected_document_type or "document") != type_filter:
                return False

        if source_filter != "all":
            if (document.source_provider or document.source_origin) != source_filter:
                return False

        return True

    def _document_list_sort_key(self, sort_order: str):
        if sort_order == "oldest":
            return lambda item: item.uploaded_at
        if sort_order == "name":
            return lambda item: item.original_name.lower()
        if sort_order == "largest":
            return lambda item: item.size_bytes
        if sort_order == "document_date_newest":
            return lambda item: item.document_date or "1900-01-01"
        if sort_order == "document_date_oldest":
            return lambda item: item.document_date or "2999-12-31"
        return lambda item: item.uploaded_at

    def _document_list_sort_reverse(self, sort_order: str) -> bool:
        if sort_order in {"oldest", "name", "document_date_oldest"}:
            return False
        return True

    def _validate_upload_name(self, original_name: str) -> None:
        suffix = Path(original_name).suffix.lower()
        if suffix not in self.SUPPORTED_UPLOAD_EXTENSIONS:
            raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")

    def _write_stream_with_size_limit(self, *, source_file, target_path: Path) -> int:
        max_size_bytes = settings.document_upload_max_size_bytes
        chunk_size = 1024 * 1024
        total_bytes = 0

        with target_path.open("wb") as output_file:
            while True:
                chunk = source_file.read(chunk_size)
                if not chunk:
                    break

                total_bytes += len(chunk)
                if total_bytes > max_size_bytes:
                    raise ValueError(
                        "File is too large. "
                        f"Maximum supported size is {settings.document_upload_max_size_mb} MB."
                    )
                output_file.write(chunk)

        return total_bytes

    def _normalize_document_name(self, value: str) -> str:
        normalized = Path(value).stem.lower().replace("_", " ").replace("-", " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _format_document_type_label(self, value: str | None) -> str:
        if not value or value == "document":
            return "documents"
        if value == "policy":
            return "policies"
        if value == "architecture":
            return "architecture documents"
        if value == "features":
            return "feature documents"
        if value.endswith("s"):
            return value
        return f"{value}s"

    def _document_signal_score(
        self,
        document: DocumentRecord,
        query: str,
        query_terms: set[str],
    ) -> float:
        score = 0.0
        query_entity_keys = [
            self._normalize_entity_text(entity)
            for entity in self.extract_query_entities(query)
            if self._normalize_entity_text(entity)
        ]
        query_phrase_terms = self.extract_focus_terms(query)

        for signal in document.document_signals:
            normalized = getattr(signal, "normalized", "") or ""
            signal_score = float(getattr(signal, "score", 0.0) or 0.0)
            if not normalized or signal_score <= 0:
                continue

            overlap = len(query_terms & set(normalized.split()))
            if overlap:
                score = max(score, min(signal_score * (0.35 + (overlap * 0.18)), 1.0))

            if query_phrase_terms:
                phrase_overlap = len(set(query_phrase_terms) & set(normalized.split()))
                if phrase_overlap >= max(1, min(2, len(query_phrase_terms))):
                    score = max(score, min(signal_score * 0.78, 1.0))

            for query_entity_key in query_entity_keys:
                if query_entity_key and (
                    query_entity_key in normalized or normalized in query_entity_key
                ):
                    multiplier = 0.98 if signal.category == "entity" else 0.88
                    score = max(score, min(signal_score * multiplier, 1.0))

        return score

    def _document_signal_bonus(
        self,
        document: DocumentRecord,
        query: str,
        query_terms: set[str],
    ) -> int:
        signal_score = self._document_signal_score(document, query, query_terms)
        if signal_score <= 0:
            return 0

        return max(1, round(signal_score * 5))

    def _normalize_entity_text(self, value: str) -> str:
        normalized = self._strip_accents(value).lower().replace("&", " and ")
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        normalized = re.sub(
            r"\b(?:ab|aps|as|bv|gmbh|inc|llc|ltd|oy|sa|sarl|europe|europa)\b",
            " ",
            normalized,
        )
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _strip_accents(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        return "".join(character for character in normalized if not unicodedata.combining(character))

    def _document_matches_entity(
        self,
        document: DocumentRecord,
        requested_entity: str,
    ) -> bool:
        requested_key = self._normalize_entity_text(requested_entity)
        if not requested_key:
            return False

        entity_candidates = list(document.document_entities)
        entity_candidates.extend(
            signal.value
            for signal in document.document_signals
            if signal.category == "entity"
        )
        if document.document_title:
            entity_candidates.append(document.document_title)
        entity_candidates.append(Path(document.original_name).stem)

        for candidate in entity_candidates:
            candidate_key = self._normalize_entity_text(candidate)
            if not candidate_key:
                continue
            if requested_key in candidate_key or candidate_key in requested_key:
                return True

        return False

    def _format_entity_label(self, value: str | None) -> str:
        if not value:
            return ""
        return " ".join(part.capitalize() if not part.isdigit() else part for part in value.split())

    def _join_phrases(self, values: list[str]) -> str:
        items = [str(value).strip() for value in values if str(value).strip()]
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        if len(items) == 2:
            return f"{items[0]} and {items[1]}"
        return f"{', '.join(items[:-1])}, and {items[-1]}"

    def _with_indefinite_article(self, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            return value
        article = "an" if cleaned[:1].lower() in {"a", "e", "i", "o", "u"} else "a"
        return f"{article} {cleaned}"

    def _format_size_bytes(self, size_bytes: int) -> str:
        size = float(max(size_bytes, 0))
        units = ("B", "KB", "MB", "GB")
        for unit in units:
            if size < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(size)} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{int(size_bytes)} B"

    def _format_uploaded_at(self, uploaded_at: str | None) -> str:
        if not uploaded_at:
            return "an unknown time"
        try:
            timestamp = datetime.fromisoformat(uploaded_at)
        except ValueError:
            return uploaded_at
        return timestamp.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")

    def _document_has_signature_markers(self, document: DocumentRecord) -> bool:
        if document.document_date_kind == "signed_date":
            return True
        if any(
            marker in signal.normalized
            for signal in self._coerce_document_signals(document.document_signals)
            for marker in ("signed", "signature")
        ):
            return True
        extracted_text = self.get_extracted_text(document.id)
        if not extracted_text:
            return False
        lowered = extracted_text.lower()
        return any(
            marker in lowered
            for marker in (
                "signed by",
                "signed on",
                "signature date",
                "signature of",
                "undersigned",
                "authorized buyer",
                "authorized seller",
            )
        )

    def _document_company_candidates(self, document: DocumentRecord) -> list[str]:
        candidates: list[str] = []
        for entity in document.document_entities:
            cleaned = self._clean_company_candidate(entity)
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)

        for signal in self._coerce_document_signals(document.document_signals):
            if signal.category != "entity":
                continue
            cleaned = self._clean_company_candidate(signal.value)
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)

        extracted_text = self.get_extracted_text(document.id)
        patterns = (
            r"(?im)^(?:vendor|supplier|seller|company|customer|bill to|invoice to)\s*[:\-]\s*(.+)$",
            r"(?im)^(?:leverant[oö]r|kund)\s*[:\-]\s*(.+)$",
            r"(?im)^(?:sprzedawca\s*/\s*seller|seller|vendor|supplier|company|customer)\s*$\s*([^\n]+)$",
            r"(?im)^(?:nabywca\s*/\s*bill to|bill to|invoice to|buyer)\s*$\s*([^\n]+)$",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, extracted_text):
                cleaned = self._clean_company_candidate(match.group(1))
                if cleaned and cleaned not in candidates:
                    candidates.append(cleaned)

        for match in re.finditer(
            r"(?i)([A-Za-z][A-Za-z&.'-]*(?:[ \t]+[A-Za-z][A-Za-z&.'-]*){0,5}[ \t]+(?:AB|LLC|Ltd|GmbH|S\.?A\.?))",
            extracted_text,
        ):
            cleaned = self._clean_company_candidate(match.group(1))
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)

        unique_candidates: list[str] = []
        seen_candidates: set[str] = set()
        for candidate in candidates:
            normalized_candidate = self._strip_accents(candidate).lower()
            if normalized_candidate in seen_candidates:
                continue
            seen_candidates.add(normalized_candidate)
            unique_candidates.append(candidate)

        unique_candidates.sort(key=self._company_candidate_priority)
        return unique_candidates[:4]

    def _clean_company_candidate(self, value: str) -> str | None:
        cleaned = " ".join(str(value or "").replace("\n", " ").split()).strip(" .,:;")
        if not cleaned:
            return None

        extracted_match = re.search(
            r"([A-ZÀ-Ý][A-Za-zÀ-ÿ&.'-]+(?:[ \t]+[A-ZÀ-Ý][A-Za-zÀ-ÿ&.'-]+){0,6}[ \t]+(?:AB|LLC|Ltd|GmbH|S\.A\.|SA))\b",
            cleaned,
        )
        if extracted_match:
            cleaned = extracted_match.group(1).strip(" .,:;")

        if not self._is_likely_company_name(cleaned):
            return None
        return cleaned

    def _company_candidate_priority(self, value: str) -> tuple[int, int]:
        lowered = self._strip_accents(value).lower()
        has_company_suffix = bool(
            re.search(r"\b(?:ab|llc|ltd|gmbh|s\.a\.|sa)\b", lowered)
        )
        return (0 if has_company_suffix else 1, len(value))

    def _is_likely_company_name(self, value: str) -> bool:
        cleaned = str(value or "").strip()
        if len(cleaned.split()) < 2:
            return False
        if re.search(r"\d|[/\\|]", cleaned):
            return False
        lowered = self._strip_accents(cleaned).lower()
        if any(
            marker in lowered
            for marker in (
                "swift",
                "bic",
                "iban",
                "vat",
                "account",
                "bank",
                "paypal",
                "nexo",
                "kod cn",
                "cn code",
                "invoice",
                "invoice fs",
            )
        ):
            return False
        alpha_ratio = sum(character.isalpha() for character in cleaned) / max(len(cleaned.replace(" ", "")), 1)
        return alpha_ratio >= 0.72

    def _extract_document_product_evidence(self, document: DocumentRecord) -> list[str]:
        commercial_summary = self._coerce_commercial_summary(document.commercial_summary)
        if commercial_summary and commercial_summary.line_items:
            return [
                self._format_commercial_line_item(item, commercial_summary.currency)
                for item in commercial_summary.line_items[:6]
            ]

        extracted_text = self._normalize_text_fragment(self.get_extracted_text(document.id))
        if not extracted_text:
            return []

        normalized = " ".join(extracted_text.split())
        evidences: list[str] = []
        patterns = (
            r"(?i)(?:product|item|description)\s*[:\-]\s*([A-Za-z][A-Za-z0-9 /(),-]{2,80})",
            r"(?i)barcode\s+([A-Za-z][A-Za-z0-9 /(),-]{2,60})\s+(?:quantity|qty|ilość|ilosc)\b",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, normalized):
                cleaned = match.group(1).strip(" .,:;")
                if cleaned and cleaned not in evidences:
                    evidences.append(cleaned)

        if evidences:
            return evidences[:4]

        fallback_phrases = (
            "bicycle part",
            "spare part",
            "service fee",
            "license",
            "subscription",
        )
        lowered = normalized.lower()
        for phrase in fallback_phrases:
            if phrase in lowered:
                evidences.append(phrase.title() if phrase != "bicycle part" else "Bicycle part")

        return evidences[:4]

    def _format_commercial_line_item(
        self,
        item: DocumentCommercialLineItem,
        fallback_currency: str | None = None,
    ) -> str:
        details: list[str] = []
        if item.quantity is not None:
            details.append(f"qty {self._format_commercial_number(item.quantity)}")
        if item.unit_price is not None:
            details.append(
                "unit "
                + self._format_commercial_money(
                    item.unit_price,
                    item.currency or fallback_currency,
                )
            )
        if item.total is not None:
            details.append(
                "total "
                + self._format_commercial_money(
                    item.total,
                    item.currency or fallback_currency,
                )
            )
        if not details:
            return item.description
        return f"{item.description} ({', '.join(details)})"

    def _format_commercial_money(
        self,
        value: float,
        currency: str | None = None,
    ) -> str:
        formatted = self._format_commercial_number(value)
        return f"{formatted} {currency}" if currency else formatted

    def _format_commercial_number(self, value: float) -> str:
        if float(value).is_integer():
            return str(int(value))
        return f"{value:.2f}".rstrip("0").rstrip(".")

    def _format_commercial_summary_suffix(
        self,
        summary: DocumentCommercialSummary | None,
    ) -> str:
        if not summary:
            return ""
        details: list[str] = []
        if summary.invoice_number:
            details.append(f"invoice {summary.invoice_number}")
        if summary.invoice_date:
            details.append(f"invoice date {summary.invoice_date}")
        if summary.due_date:
            details.append(f"due {summary.due_date}")
        if summary.total is not None:
            details.append(
                "total "
                + self._format_commercial_money(summary.total, summary.currency)
            )
        return f" ({', '.join(details)})" if details else ""

    def _summarize_products_for_documents(
        self,
        documents: list[DocumentRecord],
    ) -> str:
        product_map: list[tuple[DocumentRecord, list[str]]] = []
        commercial_summaries: list[tuple[DocumentRecord, DocumentCommercialSummary]] = []
        empty_documents: list[DocumentRecord] = []
        for document in documents:
            commercial_summary = self._coerce_commercial_summary(document.commercial_summary)
            if commercial_summary:
                commercial_summaries.append((document, commercial_summary))
            evidences = self._extract_document_product_evidence(document)
            if evidences:
                product_map.append((document, evidences))
            else:
                empty_documents.append(document)

        if not product_map:
            if commercial_summaries:
                if len(commercial_summaries) == 1:
                    document, summary = commercial_summaries[0]
                    suffix = self._format_commercial_summary_suffix(summary)
                    return (
                        f"I found invoice-style details in {document.original_name}{suffix}, "
                        "but I could not find a clear product line list in the extracted text."
                    )
                leading_details = "; ".join(
                    f"{document.original_name}{self._format_commercial_summary_suffix(summary)}"
                    for document, summary in commercial_summaries[:4]
                )
                return (
                    f"I found invoice-style details in {len(commercial_summaries)} documents: "
                    f"{leading_details}. I could not find clear product line lists in those extracted texts."
                )
            if len(documents) == 1:
                return (
                    f"I could not find a clear product list in {documents[0].original_name}. "
                    "The extracted text does not expose specific ordered items."
                )
            return (
                f"I checked {len(documents)} related documents, but I could not find a clear product list in the extracted text."
            )

        if len(documents) == 1:
            document, evidences = product_map[0]
            lead = self._join_phrases(evidences[:3])
            summary = self._coerce_commercial_summary(document.commercial_summary)
            suffix = self._format_commercial_summary_suffix(summary)
            if summary and len(summary.line_items) > 1:
                return (
                    f"The ordered items I found in {document.original_name}{suffix} are: "
                    f"{lead}."
                )
            return (
                f"The clearest ordered item in {document.original_name}{suffix} is {lead}. "
                "I do not see a more detailed product list in the extracted text."
            )

        leading_details = "; ".join(
            f"{document.original_name}{self._format_commercial_summary_suffix(self._coerce_commercial_summary(document.commercial_summary))}: {self._join_phrases(evidences[:2])}"
            for document, evidences in product_map[:3]
        )
        response = (
            f"I found product-style information in {len(product_map)} of {len(documents)} related documents. "
            f"The clearest matches are {leading_details}."
        )
        if empty_documents:
            response += (
                f" {len(empty_documents)} related documents only expose totals or status without item details."
            )
        return response

    def _summarize_document_findings(
        self,
        *,
        query: str,
        category: str,
        history: list[ChatHistoryMessage] | None,
        allowed_document_ids: list[str] | None,
        is_admin: bool,
        viewer_username: str | None,
    ) -> str | None:
        label = self._finding_label(category)
        target_document = self.resolve_primary_document(
            query,
            history=history,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if target_document is not None:
            findings = self._extract_document_findings(target_document, category)
            if findings:
                return (
                    f"The clearest {label} in {target_document.original_name} are: "
                    f"{self._join_phrases(findings[:4])}."
                )
            return (
                f"I did not find clear {label} in {target_document.original_name}."
            )

        allowed_document_id_set = set(allowed_document_ids or [])
        documents = [
            document
            for document in self._filter_documents_for_viewer(
                self.list_documents(),
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if document.processing_status == "processed"
            and (not allowed_document_id_set or document.id in allowed_document_id_set)
        ]
        document_findings: list[tuple[DocumentRecord, list[str]]] = []
        for document in documents:
            findings = self._extract_document_findings(document, category)
            if findings:
                document_findings.append((document, findings))

        if not document_findings:
            return f"I did not find clear {label} in the uploaded documents."

        leading_details = "; ".join(
            f"{document.original_name}: {findings[0]}"
            for document, findings in document_findings[:4]
        )
        if len(document_findings) == 1:
            return f"I found {label} in {leading_details}."

        extra_count = len(document_findings) - 4
        suffix = f", plus {extra_count} more documents" if extra_count > 0 else ""
        return (
            f"I found {label} in {len(document_findings)} documents: "
            f"{leading_details}{suffix}."
        )

    def _extract_code_function_names(self, document: DocumentRecord) -> list[str]:
        extracted_text = self._normalize_text_fragment(self.get_extracted_text(document.id))
        if not extracted_text:
            return []

        patterns = (
            r"(?m)^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            r"(?m)^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
            r"(?m)^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(",
        )
        names: list[str] = []
        seen: set[str] = set()
        for pattern in patterns:
            for match in re.finditer(pattern, extracted_text):
                name = match.group(1).strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                names.append(name)
        return names

    def _extract_document_findings(
        self,
        document: DocumentRecord,
        category: str,
        limit: int = 6,
    ) -> list[str]:
        extracted_text = self._normalize_text_fragment(self.get_extracted_text(document.id))
        if not extracted_text:
            return []

        keywords = self._finding_keywords(category)
        if not keywords:
            return []

        candidates: list[tuple[int, int, str]] = []
        for index, candidate in enumerate(self._document_finding_candidates(extracted_text)):
            normalized = " ".join(self._strip_accents(candidate).lower().split())
            score = sum(1 for keyword in keywords if keyword in normalized)
            if category == "deadline" and self._contains_date_or_duration(normalized):
                score += 2
            if category == "decision" and re.search(r"\b(?:approved|accepted|rejected|selected|decided)\b", normalized):
                score += 1
            if score <= 0:
                continue
            candidates.append((score, index, candidate))

        candidates.sort(key=lambda item: (-item[0], item[1]))
        findings: list[str] = []
        seen: set[str] = set()
        for _score, _index, candidate in candidates:
            cleaned = self._clean_finding_text(candidate)
            normalized_cleaned = self._strip_accents(cleaned).lower()
            if not cleaned or normalized_cleaned in seen:
                continue
            seen.add(normalized_cleaned)
            findings.append(cleaned)
            if len(findings) >= limit:
                break

        return findings

    def _document_finding_candidates(self, text: str) -> list[str]:
        normalized_text = text.replace("\r", "\n")
        candidates: list[str] = []
        for line in normalized_text.splitlines():
            cleaned = " ".join(line.split()).strip(" -:")
            if 8 <= len(cleaned) <= 280:
                candidates.append(cleaned)

        paragraph_text = " ".join(normalized_text.split())
        for sentence in re.split(r"(?<=[.!?])\s+|;\s+", paragraph_text):
            cleaned = " ".join(sentence.split()).strip(" -:")
            if 8 <= len(cleaned) <= 280:
                candidates.append(cleaned)

        return candidates

    def _finding_keywords(self, category: str) -> tuple[str, ...]:
        if category == "risk":
            return (
                "risk",
                "issue",
                "incident",
                "problem",
                "blocker",
                "blocked",
                "failure",
                "failed",
                "vulnerability",
                "concern",
                "delayed",
                "overdue",
                "threshold",
                "quarantine",
                "quarantined",
                "risker",
                "forsenad",
                "beroende",
            )
        if category == "action":
            return (
                "action",
                "todo",
                "to do",
                "follow up",
                "next step",
                "recommendation",
                "recommend",
                "replace",
                "review",
                "must",
                "should",
                "required",
                "owner",
                "assigned",
                "submit",
                "submitted",
                "atgard",
                "nasta steg",
                "ansvarig",
            )
        if category == "decision":
            return (
                "decision",
                "decided",
                "approved",
                "approval",
                "accepted",
                "rejected",
                "selected",
                "agreed",
                "chosen",
                "go/no-go",
                "beslut",
                "godkand",
            )
        if category == "deadline":
            return (
                "deadline",
                "due",
                "due date",
                "valid until",
                "expires",
                "expiry",
                "renewal",
                "within",
                "notice",
                "lead time",
                "submitted within",
                "forfall",
                "giltig",
                "senast",
            )
        return ()

    def _finding_label(self, category: str) -> str:
        if category == "risk":
            return "risk markers"
        if category == "action":
            return "action items"
        if category == "decision":
            return "decision markers"
        if category == "deadline":
            return "deadline markers"
        return "findings"

    def _contains_date_or_duration(self, value: str) -> bool:
        return bool(
            re.search(
                r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,3}\s+(?:business\s+)?(?:days?|weeks?|months?)\b|\b(?:seven|fourteen|thirty|sixty|twenty[- ]one)\s+days?\b",
                value,
            )
        )

    def _clean_finding_text(self, value: str) -> str:
        cleaned = " ".join(str(value or "").split()).strip(" .,:;")
        if len(cleaned) > 220:
            cleaned = f"{cleaned[:217].rstrip()}..."
        return cleaned

    def _document_entity_fragment(
        self,
        document: DocumentRecord,
        requested_entity: str | None,
        prefix: str = " ",
    ) -> str:
        if not requested_entity:
            return ""

        for entity in document.document_entities:
            candidate_key = self._normalize_entity_text(entity)
            requested_key = self._normalize_entity_text(requested_entity)
            if requested_key and candidate_key and (
                requested_key in candidate_key or candidate_key in requested_key
            ):
                return f"{prefix}({entity})"

        return ""

    def _query_terms(self, query: str) -> list[str]:
        raw_terms = re.findall(
            r"[A-Za-z]+\d+|\d+[A-Za-z]+|[A-Za-z0-9]{3,}",
            query.lower(),
        )
        ignored_terms = {
            "the",
            "and",
            "for",
            "with",
            "this",
            "that",
            "from",
            "what",
            "how",
            "are",
            "you",
            "your",
            "det",
            "och",
            "att",
            "som",
            "hur",
            "vad",
            "kan",
            "har",
            "den",
            "ett",
            "does",
            "have",
            "any",
            "there",
            "very",
            "which",
            "into",
            "kind",
            "scanned",
            "scan",
            "handwritten",
            "image",
            "photo",
            "pdf",
            "contains",
            "contain",
            "about",
            "talks",
            "talk",
            "say",
            "says",
            "said",
            "tell",
            "show",
            "list",
            "mention",
            "mentions",
            "file",
            "files",
            "document",
            "documents",
            "uploaded",
            "upload",
            "mina",
            "visa",
            "vilka",
            "filer",
            "dokument",
            "laddat",
            "upp",
        }
        deduped_terms: list[str] = []
        seen_terms: set[str] = set()
        for term in raw_terms:
            if term in ignored_terms or term in seen_terms:
                continue
            seen_terms.add(term)
            deduped_terms.append(term)
        return deduped_terms

    def _reference_query_terms(self, value: str) -> list[str]:
        raw_terms = re.findall(
            r"[a-z0-9]{2,}",
            self._normalize_document_name(value),
        )
        ignored_terms = {
            "the",
            "and",
            "for",
            "with",
            "this",
            "that",
            "what",
            "which",
            "does",
            "have",
            "did",
            "about",
            "tell",
            "show",
            "list",
            "find",
            "some",
            "any",
            "very",
            "only",
            "can",
            "you",
            "are",
            "is",
            "it",
            "simular",
            "similar",
            "same",
            "overlap",
            "duplicate",
            "duplicates",
            "latest",
            "lataste",
            "recent",
            "newest",
            "last",
            "uploaded",
            "upload",
            "file",
            "files",
            "document",
            "documents",
            "mina",
            "visa",
            "vilka",
            "filer",
            "dokument",
            "senaste",
            "nyaste",
        }
        deduped_terms: list[str] = []
        seen_terms: set[str] = set()
        for term in raw_terms:
            if term in ignored_terms or term in seen_terms:
                continue
            seen_terms.add(term)
            deduped_terms.append(term)
        return deduped_terms

    def _score_chunk(self, content: str, terms: list[str]) -> int:
        lowered = content.lower()
        counts = Counter()
        for term in terms:
            hits = lowered.count(term)
            if hits:
                counts[term] = hits

        return sum(counts.values())

    def _recent_sources(
        self, processed_documents: list[DocumentRecord], limit: int
    ) -> list[ChatSource]:
        fallback_sources: list[ChatSource] = []

        for document in processed_documents[:2]:
            chunks_path = self.chunks_dir / f"{document.id}.json"
            if not chunks_path.exists():
                continue

            with chunks_path.open("r", encoding="utf-8") as file_handle:
                chunks = json.load(file_handle)

            for chunk in chunks[:2]:
                fallback_sources.append(
                    ChatSource(
                        document_id=document.id,
                        document_name=document.original_name,
                        chunk_index=int(chunk.get("index", 0)),
                        score=1,
                        excerpt=str(chunk.get("content", ""))[:280],
                        section_title=self._normalize_optional_text(
                            chunk.get("section_title")
                        ),
                        page_number=self._normalize_optional_int(
                            chunk.get("page_number")
                        ),
                        source_kind=self._normalize_optional_text(
                            chunk.get("source_kind")
                        ),
                        ocr_used=bool(document.ocr_used),
                    )
                )

                if len(fallback_sources) >= limit:
                    return fallback_sources

        return fallback_sources

    def _should_use_recent_document_fallback(
        self, query: str, processed_documents: list[DocumentRecord]
    ) -> bool:
        if not processed_documents:
            return False

        if self.is_document_reference_query(query):
            return True

        return False

    def _build_source_excerpt(
        self,
        chunks: list[dict[str, str | int]],
        chunk_index: int,
        query_terms: list[str],
        max_characters: int = 360,
    ) -> str:
        chunk_lookup = {
            int(chunk.get("index", 0)): {
                "content": str(chunk.get("content", "")),
                "section_title": self._normalize_optional_text(
                    chunk.get("section_title")
                ),
                "page_number": self._normalize_optional_int(chunk.get("page_number")),
            }
            for chunk in chunks
        }
        neighboring_parts = [
            str(chunk_lookup[index].get("content", ""))
            for index in (chunk_index - 1, chunk_index, chunk_index + 1)
            if index in chunk_lookup
        ]
        combined_text = " ".join(part.strip() for part in neighboring_parts if part.strip())
        normalized_text = " ".join(
            self._normalize_text_fragment(combined_text).split()
        )
        if not normalized_text:
            return ""

        if not query_terms:
            return normalized_text[:max_characters]

        lowered = normalized_text.lower()
        match_positions = [
            lowered.find(term)
            for term in query_terms
            if lowered.find(term) >= 0
        ]
        if not match_positions:
            return normalized_text[:max_characters]

        match_start = min(match_positions)
        window_half = max_characters // 2
        start = max(match_start - window_half, 0)
        end = min(start + max_characters, len(normalized_text))
        start = max(end - max_characters, 0)
        excerpt = normalized_text[start:end].strip()

        if start > 0:
            excerpt = f"...{excerpt}"
        if end < len(normalized_text):
            excerpt = f"{excerpt}..."

        return excerpt

    def _select_preview_chunks(
        self,
        chunks: list[dict[str, str | int]],
        focus_chunk_index: int,
        max_chunks: int,
    ) -> list[dict[str, str | int]]:
        chunk_lookup = {int(chunk.get("index", 0)): chunk for chunk in chunks}
        if focus_chunk_index not in chunk_lookup:
            return chunks[:max_chunks]

        half_window = max(max_chunks // 2, 1)
        selected_indices = [
            index
            for index in range(
                max(focus_chunk_index - half_window, 0),
                focus_chunk_index + half_window + 1,
            )
            if index in chunk_lookup
        ]
        return [chunk_lookup[index] for index in selected_indices[:max_chunks]]

    def _resolve_similarity_target_document_ids(
        self,
        query: str | None,
        history: list[ChatHistoryMessage],
        processed_documents: list[DocumentRecord],
    ) -> list[str]:
        if query and self.is_broad_similarity_inventory_query(query):
            return []

        if query:
            matched_ids = self.find_referenced_documents(query)
            if matched_ids:
                return matched_ids[:2]

        for message in reversed(history[-8:]):
            source_document_ids = [
                source.document_id
                for source in message.sources
                if getattr(source, "document_id", None)
            ]
            if source_document_ids:
                unique_ids: list[str] = []
                for document_id in source_document_ids:
                    if document_id not in unique_ids:
                        unique_ids.append(document_id)
                if unique_ids:
                    return unique_ids[:2]

            if message.content:
                matched_ids = self.find_referenced_documents(message.content)
                if matched_ids:
                    return matched_ids[:2]

        if query and processed_documents:
            query_theme_ids = self._find_query_theme_documents(
                query=query,
                processed_documents=processed_documents,
            )
            if query_theme_ids:
                return query_theme_ids[:2]

            semantic_ids = self._find_semantically_referenced_documents(
                query=query,
                processed_documents=processed_documents,
            )
            if semantic_ids:
                return semantic_ids[:2]

        return []

    def _summarize_documents_similar_to_target(
        self,
        processed_documents: list[DocumentRecord],
        target_documents: list[DocumentRecord],
        query: str | None,
        minimum_score: float,
    ) -> str:
        target_document = target_documents[0]
        cached_candidates = self._cached_similarity_candidates(
            target_document,
            processed_documents,
        )
        if cached_candidates and cached_candidates[0][0] >= minimum_score:
            strongest_score, strongest_document, shared_terms = cached_candidates[0]
            return self._render_similarity_summary(
                target_document=target_document,
                strongest_document=strongest_document,
                strongest_score=strongest_score,
                shared_terms=shared_terms,
            )

        target_profile = self._build_document_similarity_profile(target_document)
        candidate_documents = [
            document
            for document in processed_documents
            if document.id != target_document.id
        ]
        if not candidate_documents:
            return (
                f"I could not find any other uploaded documents to compare with "
                f"{target_document.original_name}."
            )

        target_terms = self._document_term_set(target_document.id)
        target_signals = self._document_signal_term_set(target_document)
        profile_texts = [target_profile] + [
            self._build_document_similarity_profile(document)
            for document in candidate_documents
        ]
        embeddings = self.embedding_service.embed_texts(profile_texts)
        target_embedding = embeddings[0] if len(embeddings) == len(profile_texts) else []
        candidate_embeddings = embeddings[1:] if len(embeddings) == len(profile_texts) else []

        candidates: list[tuple[float, DocumentRecord, list[str]]] = []
        for index, document in enumerate(candidate_documents):
            semantic_score = 0.0
            if target_embedding and candidate_embeddings:
                semantic_score = self._cosine_similarity(
                    target_embedding,
                    candidate_embeddings[index],
                )

            text_score = self._jaccard_similarity(
                target_terms,
                self._document_term_set(document.id),
            )
            signal_score = self._jaccard_similarity(
                target_signals,
                self._document_signal_term_set(document),
            )
            type_bonus = (
                0.08
                if target_document.detected_document_type
                and target_document.detected_document_type == document.detected_document_type
                else 0.0
            )
            entity_bonus = (
                0.05
                if set(target_document.document_entities) & set(document.document_entities)
                else 0.0
            )
            combined_score = (
                (semantic_score * 0.62)
                + (text_score * 0.2)
                + (signal_score * 0.1)
                + type_bonus
                + entity_bonus
            )
            if signal_score == 0 and text_score < 0.02 and semantic_score < 0.58:
                continue
            if combined_score < minimum_score:
                continue

            shared_terms = self._shared_document_theme_terms(
                target_document,
                document,
                query=query,
            )
            candidates.append((combined_score, document, shared_terms))

        if not candidates:
            return (
                f"I did not find any uploaded documents that look thematically close to "
                f"{target_document.original_name}."
            )

        candidates.sort(key=lambda item: item[0], reverse=True)
        strongest_score, strongest_document, shared_terms = candidates[0]
        return self._render_similarity_summary(
            target_document=target_document,
            strongest_document=strongest_document,
            strongest_score=strongest_score,
            shared_terms=shared_terms,
        )

    def _refresh_similarity_cache_for_document(
        self,
        document: DocumentRecord,
        *,
        extracted_text: str,
    ) -> None:
        document.similarity_profile = self._build_document_similarity_profile(
            document,
            sample_text=extracted_text,
        )
        document.similarity_terms = self._build_similarity_terms(
            document,
            extracted_text=extracted_text,
        )

        processed_documents = [
            candidate
            for candidate in self.list_documents()
            if candidate.id != document.id and candidate.processing_status == "processed"
        ]
        document.similar_documents = self._rank_similar_documents(
            document,
            processed_documents,
            limit=6,
            minimum_score=0.2,
        )
        document.similarity_updated_at = datetime.now(UTC).isoformat()
        self._store_reverse_similarity_links(document, processed_documents)

    def _store_reverse_similarity_links(
        self,
        source_document: DocumentRecord,
        candidates: list[DocumentRecord],
    ) -> None:
        candidate_lookup = {
            candidate.id: candidate
            for candidate in candidates
        }
        for match in source_document.similar_documents[:6]:
            candidate = candidate_lookup.get(match.document_id)
            if candidate is None:
                continue
            if not candidate.similarity_profile:
                candidate.similarity_profile = self._build_document_similarity_profile(
                    candidate
                )
            if not candidate.similarity_terms:
                candidate.similarity_terms = self._build_similarity_terms(candidate)
            candidate.similar_documents = self._upsert_similarity_match(
                candidate.similar_documents,
                DocumentSimilarityMatch(
                    document_id=source_document.id,
                    document_name=source_document.original_name,
                    score=match.score,
                    shared_terms=match.shared_terms,
                    reason=match.reason,
                ),
                limit=6,
            )
            candidate.similarity_updated_at = datetime.now(UTC).isoformat()
            self._write_metadata(candidate)

    def _upsert_similarity_match(
        self,
        existing_matches: list[DocumentSimilarityMatch],
        new_match: DocumentSimilarityMatch,
        *,
        limit: int,
    ) -> list[DocumentSimilarityMatch]:
        merged: list[DocumentSimilarityMatch] = [
            match
            for match in self._coerce_document_similarity_matches(existing_matches)
            if match.document_id != new_match.document_id
        ]
        merged.append(new_match)
        return self._coerce_document_similarity_matches(merged)[:limit]

    def _rank_similar_documents(
        self,
        target_document: DocumentRecord,
        candidate_documents: list[DocumentRecord],
        *,
        limit: int,
        minimum_score: float,
    ) -> list[DocumentSimilarityMatch]:
        target_terms = self._document_similarity_term_set(target_document)
        target_signals = self._document_signal_term_set(target_document)
        target_title = self._normalize_document_name(
            f"{target_document.original_name} {target_document.document_title or ''}"
        )

        ranked: list[DocumentSimilarityMatch] = []
        for candidate in candidate_documents:
            if candidate.processing_status != "processed":
                continue

            candidate_terms = self._document_similarity_term_set(candidate)
            candidate_signals = self._document_signal_term_set(candidate)
            text_score = self._jaccard_similarity(target_terms, candidate_terms)
            signal_score = self._jaccard_similarity(target_signals, candidate_signals)
            title_score = SequenceMatcher(
                None,
                target_title,
                self._normalize_document_name(
                    f"{candidate.original_name} {candidate.document_title or ''}"
                ),
            ).ratio()
            type_bonus = (
                0.08
                if target_document.detected_document_type
                and target_document.detected_document_type == candidate.detected_document_type
                else 0.0
            )
            entity_bonus = (
                0.05
                if set(target_document.document_entities) & set(candidate.document_entities)
                else 0.0
            )
            overlap_bonus = min(len(target_terms & candidate_terms), 6) * 0.015
            combined_score = (
                (text_score * 0.52)
                + (signal_score * 0.18)
                + (title_score * 0.12)
                + type_bonus
                + entity_bonus
                + overlap_bonus
            )
            if signal_score == 0 and text_score < 0.06 and title_score < 0.42:
                continue
            if combined_score < minimum_score:
                continue

            shared_terms = self._shared_document_theme_terms(target_document, candidate)
            ranked.append(
                DocumentSimilarityMatch(
                    document_id=candidate.id,
                    document_name=candidate.original_name,
                    score=round(max(0.0, min(combined_score, 1.0)), 4),
                    shared_terms=shared_terms[:4],
                    reason=self._similarity_reason(
                        target_document,
                        candidate,
                        shared_terms,
                    ),
                )
            )

        return self._coerce_document_similarity_matches(ranked)[:limit]

    def _cached_similarity_candidates(
        self,
        target_document: DocumentRecord,
        processed_documents: list[DocumentRecord],
    ) -> list[tuple[float, DocumentRecord, list[str]]]:
        if not target_document.similar_documents:
            return []

        candidate_lookup = {
            document.id: document
            for document in processed_documents
            if document.id != target_document.id
        }
        ranked: list[tuple[float, DocumentRecord, list[str]]] = []
        for match in self._coerce_document_similarity_matches(
            target_document.similar_documents
        ):
            candidate = candidate_lookup.get(match.document_id)
            if candidate is None:
                continue
            ranked.append((match.score, candidate, match.shared_terms))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked

    def _render_similarity_summary(
        self,
        *,
        target_document: DocumentRecord,
        strongest_document: DocumentRecord,
        strongest_score: float,
        shared_terms: list[str],
    ) -> str:
        shared_theme = ", ".join(shared_terms[:3]) if shared_terms else "overall topic"
        similarity_percent = round(min(max(strongest_score, 0.0), 1.0) * 100)
        lead = (
            f"The closest related document to {target_document.original_name} is "
            f"{strongest_document.original_name}."
        )
        detail = (
            f" They overlap around {shared_theme}, with an estimated similarity of about"
            f" {similarity_percent}%."
        )
        return lead + detail

    def _similarity_reason(
        self,
        left_document: DocumentRecord,
        right_document: DocumentRecord,
        shared_terms: list[str],
    ) -> str:
        if shared_terms:
            return "Shared themes: " + ", ".join(shared_terms[:3])
        if (
            left_document.detected_document_type
            and left_document.detected_document_type == right_document.detected_document_type
        ):
            return f"Same document type: {left_document.detected_document_type}"
        if set(left_document.document_entities) & set(right_document.document_entities):
            return "Overlapping named entities"
        return "General thematic overlap"

    def _derive_document_family_key(self, document: DocumentRecord) -> str | None:
        base_name = Path(document.original_name).stem
        candidate = document.document_title or base_name
        normalized = self._normalize_document_name(candidate)
        normalized = re.sub(r"^\d{8}-\d{6}-", "", normalized)
        normalized = re.sub(
            r"\b20\d{2}[._-]?(?:0[1-9]|1[0-2])(?:[._-]?(?:0[1-9]|[12]\d|3[01]))?\b",
            " ",
            normalized,
        )
        normalized = re.sub(
            r"\b(?:v|ver|version|rev|revision)[._ -]*\d+\b",
            " ",
            normalized,
        )
        normalized = re.sub(r"\b(?:copy|final|draft)\b", " ", normalized)
        normalized = re.sub(r"[_-]+", " ", normalized)
        normalized = " ".join(normalized.split())
        if not normalized or len(normalized) < 4:
            return None
        return normalized[:120]

    def _derive_document_family_label(self, document: DocumentRecord) -> str | None:
        family_key = self._derive_document_family_key(document)
        if not family_key:
            return None

        candidate = document.document_title or Path(document.original_name).stem
        candidate = re.sub(r"^\d{8}-\d{6}-", "", candidate).strip()
        candidate = re.sub(
            r"\b(?:v|ver|version|rev|revision)[._ -]*\d+\b",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = re.sub(
            r"\b20\d{2}[._-]?(?:0[1-9]|1[0-2])(?:[._-]?(?:0[1-9]|[12]\d|3[01]))?\b",
            "",
            candidate,
        )
        candidate = " ".join(candidate.replace("_", " ").replace("-", " ").split())
        return candidate[:120] if candidate else family_key.title()

    def _derive_document_version(
        self,
        document: DocumentRecord,
    ) -> tuple[str | None, int | None]:
        searchable = " ".join(
            part
            for part in [
                document.original_name,
                document.document_title or "",
                document.document_date or "",
            ]
            if part
        )
        match = re.search(
            r"\b(?:v|ver|version|rev|revision)[._ -]*(\d{1,4})\b",
            searchable,
            flags=re.IGNORECASE,
        )
        if match:
            version_number = int(match.group(1))
            return (f"v{version_number}", version_number)

        if document.document_date:
            digits = re.sub(r"\D+", "", document.document_date)
            if digits:
                try:
                    return (document.document_date, int(digits[:8]))
                except ValueError:
                    return (document.document_date, None)

        return (None, None)

    def _build_document_topics(
        self,
        document: DocumentRecord,
        *,
        extracted_text: str | None = None,
    ) -> list[str]:
        weighted_topics: Counter[str] = Counter()
        if document.detected_document_type and document.detected_document_type != "document":
            weighted_topics[document.detected_document_type] += 5
        if document.source_kind and document.source_kind not in {"document", "pdf"}:
            weighted_topics[document.source_kind] += 2

        for entity in document.document_entities[:5]:
            normalized = self._normalize_entity_text(entity)
            if normalized:
                weighted_topics[normalized] += 3

        for signal in sorted(
            document.document_signals,
            key=lambda item: item.score,
            reverse=True,
        )[:8]:
            normalized = self._normalize_entity_text(signal.value or signal.normalized)
            if normalized and len(normalized) >= 3:
                weighted_topics[normalized] += 2 if signal.score >= 0.5 else 1

        similarity_terms = self._build_similarity_terms(
            document,
            extracted_text=extracted_text,
        )
        for term in similarity_terms[:8]:
            if len(term) >= 4:
                weighted_topics[term] += 1

        return [topic for topic, _ in weighted_topics.most_common(6)]

    def _derive_document_summary_anchor(
        self,
        document: DocumentRecord,
        *,
        extracted_text: str | None = None,
    ) -> str | None:
        if document.document_entities:
            return document.document_entities[0]

        strong_signals = [
            signal.value
            for signal in sorted(
                document.document_signals,
                key=lambda item: item.score,
                reverse=True,
            )
            if signal.value and signal.score >= 0.45
        ]
        if strong_signals:
            return strong_signals[0]

        topics = self._build_document_topics(document, extracted_text=extracted_text)
        if topics:
            return topics[0]

        return None

    def _build_document_similarity_profile(
        self,
        document: DocumentRecord,
        *,
        sample_text: str | None = None,
    ) -> str:
        if sample_text is None and document.similarity_profile:
            return document.similarity_profile

        parts = [
            f"name: {document.original_name}",
            f"type: {document.detected_document_type or 'document'}",
        ]
        if document.document_title:
            parts.append(f"title: {document.document_title}")
        if document.document_date:
            parts.append(f"date: {document.document_date}")
        if document.document_family_label:
            parts.append(f"family: {document.document_family_label}")
        if document.document_version_label:
            parts.append(f"version: {document.document_version_label}")
        if document.document_entities:
            parts.append(
                "entities: " + ", ".join(document.document_entities[:5])
            )
        if document.document_topics:
            parts.append("topics: " + ", ".join(document.document_topics[:6]))
        if document.commercial_summary:
            commercial_parts = self._commercial_summary_profile_parts(
                document.commercial_summary
            )
            if commercial_parts:
                parts.append("commercial: " + "; ".join(commercial_parts))

        top_signals = [
            signal.value
            for signal in sorted(
                document.document_signals,
                key=lambda item: item.score,
                reverse=True,
            )[:10]
        ]
        if top_signals:
            parts.append("signals: " + ", ".join(top_signals))

        sample = sample_text
        if sample is None:
            extracted_path = self.extracted_text_dir / f"{document.id}.txt"
            if extracted_path.exists():
                sample = extracted_path.read_text(encoding="utf-8")
        if sample:
            parts.append("sample: " + self._normalize_text_fragment(sample[:1200]))

        return "\n".join(parts)

    def _commercial_summary_profile_parts(
        self,
        summary: DocumentCommercialSummary,
    ) -> list[str]:
        parts: list[str] = []
        if summary.invoice_number:
            parts.append(f"invoice number {summary.invoice_number}")
        if summary.invoice_date:
            parts.append(f"invoice date {summary.invoice_date}")
        if summary.due_date:
            parts.append(f"due date {summary.due_date}")
        if summary.total is not None:
            parts.append(
                f"total {self._format_commercial_money(summary.total, summary.currency)}"
            )
        if summary.line_items:
            item_descriptions = [
                item.description
                for item in summary.line_items[:6]
                if item.description
            ]
            if item_descriptions:
                parts.append("items " + ", ".join(item_descriptions))
        return parts

    def _build_similarity_terms(
        self,
        document: DocumentRecord,
        *,
        extracted_text: str | None = None,
    ) -> list[str]:
        ignored_terms = {
            "about",
            "after",
            "assistant",
            "before",
            "chapter",
            "content",
            "document",
            "documents",
            "file",
            "files",
            "from",
            "page",
            "pages",
            "sample",
            "section",
            "source",
            "text",
            "title",
            "uploaded",
            "with",
        }
        weighted_terms: Counter[str] = Counter()

        def add_terms(value: str, weight: int) -> None:
            normalized = self._normalize_text_fragment(value)
            for term in self._query_terms(normalized):
                if len(term) < 4 or term in ignored_terms:
                    continue
                weighted_terms[term] += weight

        add_terms(document.original_name, 5)
        if document.document_title:
            add_terms(document.document_title, 5)
        if document.detected_document_type:
            add_terms(document.detected_document_type, 3)
        if document.source_kind:
            add_terms(document.source_kind, 2)

        for entity in document.document_entities[:10]:
            add_terms(entity, 4)

        for signal in sorted(
            document.document_signals,
            key=lambda item: item.score,
            reverse=True,
        )[:12]:
            signal_weight = 4 if signal.score >= 0.5 else 2
            add_terms(signal.normalized or signal.value, signal_weight)

        sample = extracted_text
        if sample is None:
            extracted_path = self.extracted_text_dir / f"{document.id}.txt"
            if extracted_path.exists():
                sample = extracted_path.read_text(encoding="utf-8")
        if sample:
            add_terms(sample[:4000], 1)

        return [term for term, _ in weighted_terms.most_common(40)]

    def _document_signal_term_set(self, document: DocumentRecord) -> set[str]:
        normalized_terms: set[str] = set()
        for signal in document.document_signals:
            if signal.score < 0.35:
                continue
            normalized = (signal.normalized or "").strip()
            if not normalized:
                continue
            normalized_terms.add(normalized)
        return normalized_terms

    def _document_theme_term_set(self, document: DocumentRecord) -> set[str]:
        ignored_terms = {
            "about",
            "after",
            "agreement",
            "all",
            "anna",
            "and",
            "any",
            "archive",
            "author",
            "before",
            "chapter",
            "company",
            "document",
            "from",
            "guide",
            "manual",
            "name",
            "page",
            "part",
            "published",
            "publishing",
            "section",
            "software",
            "that",
            "their",
            "this",
            "title",
            "with",
        }
        theme_terms: set[str] = set()

        cached_terms = {
            term
            for term in self._document_similarity_term_set(document)
            if len(term) >= 4 and term not in ignored_terms
        }
        if cached_terms:
            return cached_terms

        for signal in document.document_signals:
            if signal.score < 0.42:
                continue
            for term in signal.normalized.split():
                if len(term) < 4 or term in ignored_terms:
                    continue
                theme_terms.add(term)

        if theme_terms:
            return theme_terms

        return {
            term
            for term in self._document_term_set(document.id)
            if len(term) >= 4 and term not in ignored_terms
        }

    def _document_similarity_term_set(self, document: DocumentRecord) -> set[str]:
        normalized_terms = self._normalize_similarity_terms(document.similarity_terms)
        if normalized_terms:
            return set(normalized_terms)
        return set(self._build_similarity_terms(document))

    def _shared_document_theme_terms(
        self,
        left_document: DocumentRecord,
        right_document: DocumentRecord,
        query: str | None = None,
    ) -> list[str]:
        if query:
            query_terms = [
                term
                for term in self._query_terms(self._normalize_text_fragment(query))
                if len(term) >= 4
            ]
            if query_terms:
                left_terms = self._document_theme_term_set(left_document)
                right_terms = self._document_theme_term_set(right_document)
                shared_query_terms = [
                    term
                    for term in query_terms
                    if term in left_terms and term in right_terms
                ]
                if shared_query_terms:
                    return shared_query_terms[:4]

        shared_entities = [
            entity
            for entity in left_document.document_entities
            if entity in right_document.document_entities
        ]
        if shared_entities:
            return shared_entities[:4]

        left_signals = {
            signal.normalized: signal.value
            for signal in left_document.document_signals
            if signal.score >= 0.35
        }
        shared_signals = [
            left_signals[normalized]
            for normalized in left_signals
            if normalized in self._document_signal_term_set(right_document)
        ]
        if shared_signals:
            return shared_signals[:4]

        left_terms = self._document_theme_term_set(left_document)
        right_terms = self._document_theme_term_set(right_document)
        return sorted(left_terms & right_terms)[:4]

    def _find_semantically_referenced_documents(
        self,
        query: str,
        processed_documents: list[DocumentRecord],
    ) -> list[str]:
        profile_texts = [query] + [
            self._build_document_similarity_profile(document)
            for document in processed_documents
        ]
        embeddings = self.embedding_service.embed_texts(profile_texts)
        if len(embeddings) != len(profile_texts):
            return []

        query_embedding = embeddings[0]
        ranked: list[tuple[float, str]] = []
        for document, embedding in zip(processed_documents, embeddings[1:], strict=False):
            score = self._cosine_similarity(query_embedding, embedding)
            if score < 0.42:
                continue
            ranked.append((score, document.id))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [document_id for _, document_id in ranked[:2]]

    def _find_query_theme_documents(
        self,
        query: str,
        processed_documents: list[DocumentRecord],
    ) -> list[str]:
        ordered_query_terms = [
            term
            for term in self._query_terms(self._normalize_text_fragment(query))
            if len(term) >= 4
        ]
        query_terms = set(ordered_query_terms)
        if not ordered_query_terms:
            return []

        lowered_query = " ".join(self._strip_accents(query).lower().split())
        ranked: list[tuple[float, str]] = []

        for document in processed_documents:
            title_terms = {
                term
                for term in re.findall(
                    r"[a-z0-9]{4,}",
                    self._normalize_document_name(
                        f"{document.original_name} {document.document_title or ''}"
                    ),
                )
            }
            theme_terms = self._document_theme_term_set(document)
            title_overlap = len(query_terms & title_terms)
            theme_overlap = len(query_terms & theme_terms)
            phrase_bonus = 0.0
            profile_text = self._build_document_similarity_profile(document).lower()
            for left_term, right_term in zip(
                ordered_query_terms,
                ordered_query_terms[1:],
                strict=False,
            ):
                phrase = f"{left_term} {right_term}"
                if phrase in lowered_query and phrase in profile_text:
                    phrase_bonus += 0.22

            score = (title_overlap * 0.28) + (theme_overlap * 0.18) + phrase_bonus
            if score < 0.4:
                continue
            ranked.append((score, document.id))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [document_id for _, document_id in ranked[:2]]

    def _cosine_similarity(
        self,
        left_vector: list[float],
        right_vector: list[float],
    ) -> float:
        if not left_vector or not right_vector or len(left_vector) != len(right_vector):
            return 0.0

        numerator = sum(left * right for left, right in zip(left_vector, right_vector, strict=False))
        left_norm = sum(value * value for value in left_vector) ** 0.5
        right_norm = sum(value * value for value in right_vector) ** 0.5
        if left_norm == 0 or right_norm == 0:
            return 0.0

        return numerator / (left_norm * right_norm)

    def _document_term_set(self, document_id: str) -> set[str]:
        extracted_path = self.extracted_text_dir / f"{document_id}.txt"
        if not extracted_path.exists():
            return set()

        content = extracted_path.read_text(encoding="utf-8")
        terms = self._query_terms(self._normalize_text_fragment(content))
        return set(terms[:300])

    def _jaccard_similarity(self, left_terms: set[str], right_terms: set[str]) -> float:
        if not left_terms or not right_terms:
            return 0.0

        intersection = left_terms & right_terms
        union = left_terms | right_terms
        if not union:
            return 0.0

        return len(intersection) / len(union)

    def _normalize_text_fragment(self, value: str) -> str:
        return re.sub(r"[\x00-\x08\x0B-\x1F\x7F]+", " ", value)

    def _normalize_optional_text(self, value: object) -> str | None:
        if value is None:
            return None

        normalized = self._normalize_text_fragment(str(value)).strip()
        return normalized or None

    def _normalize_optional_int(self, value: object) -> int | None:
        if value is None or value == "":
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None
