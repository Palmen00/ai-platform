import json
import mimetypes
import re
import shutil
from collections import Counter
from datetime import UTC, datetime
import unicodedata
from pathlib import Path
from uuid import uuid4
from difflib import SequenceMatcher

from fastapi import UploadFile

from app.config import settings
from app.schemas.document import DocumentRecord
from app.schemas.document import DocumentFacetOption
from app.schemas.document import DocumentSignal
from app.schemas.document import DocumentPreview
from app.schemas.document import DocumentPreviewChunk
from app.schemas.chat import ChatHistoryMessage, ChatSource
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
        "invoice": {"invoice", "invoices", "faktura", "fakturor", "fraktura", "frakturor"},
        "contract": {"contract", "contracts", "agreement", "agreements", "avtal", "kontrakt"},
        "insurance": {"insurance", "insurances", "policy", "policies", "försäkring", "försäkringar"},
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
        "presentation": {"presentation", "presentations", "slides", "slide deck", "ppt", "pptx"},
        "code": {"code", "source code", "script", "scripts", "repository", "repo"},
        "config": {"config", "configs", "configuration", "configurations", "settings file", "yaml", "yml", "env"},
        "document": {"document", "documents", "file", "files", "doc", "docs"},
    }

    def __init__(self) -> None:
        self.uploads_dir = settings.uploads_dir
        self.metadata_dir = settings.documents_metadata_dir
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
            for document in self._filter_documents_for_viewer(
                self.list_documents(),
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
        ]

    def find_referenced_documents(
        self,
        query: str,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> list[str]:
        normalized_query = self._normalize_document_name(query)
        query_terms = set(self.extract_query_terms(query))
        allowed_document_id_set = set(allowed_document_ids or [])
        ranked_matches: list[tuple[float, str]] = []

        for document in self._filter_documents_for_viewer(
            self.list_documents(),
            is_admin=is_admin,
            viewer_username=viewer_username,
        ):
            if allowed_document_id_set and document.id not in allowed_document_id_set:
                continue

            normalized_name = self._normalize_document_name(document.original_name)
            name_terms = set(re.findall(r"[a-z0-9]{3,}", normalized_name))
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
                - extra_term_penalty
            )

            if combined_score < 0.18:
                continue

            ranked_matches.append((combined_score, document.id))

        ranked_matches.sort(key=lambda item: item[0], reverse=True)
        return [document_id for _, document_id in ranked_matches]

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
        metadata_path = self._metadata_path(document_id)
        if not metadata_path.exists():
            return None

        with metadata_path.open("r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)

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
        document = self.get_document(document_id)
        if document is None:
            raise FileNotFoundError(f"Document {document_id} not found")

        file_path = self.uploads_dir / document.stored_name
        if not file_path.exists():
            raise FileNotFoundError(f"Stored file missing for document {document_id}")

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
            document.last_processed_at = datetime.now(UTC).isoformat()
            document.processing_error = str(exc)
            document.processing_stage = "failed"
            document.processing_updated_at = datetime.now(UTC).isoformat()
            document.indexing_status = "pending"
            document.indexed_at = None
            document.indexing_error = None
            self._remove_processing_artifacts(document.id)

        self._write_metadata(document)
        return document

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

        metadata_path = self._metadata_path(document_id)
        file_path = self.uploads_dir / document.stored_name
        if file_path.exists():
            file_path.unlink()

        self._remove_processing_artifacts(document_id)
        try:
            self.vector_store.remove_document_chunks(document_id)
        except Exception:
            pass
        metadata_path.unlink()
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
            "document",
            "documents",
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
        return any(term in lowered for term in reference_terms)

    def is_document_inventory_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        inventory_markers = (
            "what files have i uploaded",
            "which files have i uploaded",
            "what documents have i uploaded",
            "which documents have i uploaded",
            "list my files",
            "list my documents",
            "show my files",
            "show my documents",
            "visa mina filer",
            "vilka filer har jag laddat upp",
            "vilka dokument har jag laddat upp",
        )
        return any(marker in lowered for marker in inventory_markers)

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
            "have i",
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
        )
        return any(marker in lowered for marker in content_markers)

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
            "same",
            "duplicates",
            "duplicate",
            "overlap",
        )
        return self.is_document_reference_query(query) and any(
            marker in lowered for marker in similarity_markers
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
        for document_type, aliases in self.DOCUMENT_TYPE_ALIASES.items():
            if document_type == "document":
                continue
            for alias in aliases:
                match = re.search(rf"\b{re.escape(alias)}\b", lowered)
                if not match:
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

            if requested_type:
                if requested_type in {"word", "spreadsheet", "presentation"}:
                    if (document.source_kind or "document") != requested_type:
                        continue
                elif (document.detected_document_type or "document") != requested_type:
                    continue

            if requested_year:
                if not document.document_date or not document.document_date.startswith(str(requested_year)):
                    continue

            if requested_entity and not self._document_matches_entity(document, requested_entity):
                continue

            matches.append(document)

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
        if topic_phrase and len(topic_phrase.split()) >= 2:
            if topic_phrase in excerpt:
                return True

            phrase_terms = self._query_terms(topic_phrase)
            if phrase_terms:
                matched_phrase_terms = {term for term in phrase_terms if term in excerpt}
                required_matches = min(
                    len(phrase_terms),
                    max(2, len(phrase_terms) - 1),
                )
                if len(matched_phrase_terms) >= required_matches:
                    return True

        terms = self.extract_query_terms(query)
        if not terms:
            return False

        matched_terms = {term for term in terms if term in excerpt}
        if not matched_terms:
            document = self.get_document(source.document_id)
            if document is not None:
                signal_score = self._document_signal_score(document, query, set(terms))
                if signal_score >= 0.55:
                    return True
            return False

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

    def _write_metadata(self, document: DocumentRecord) -> None:
        metadata_path = self._metadata_path(document.id)
        with metadata_path.open("w", encoding="utf-8") as file_handle:
            json.dump(document.model_dump(), file_handle, ensure_ascii=True, indent=2)

    def _normalize_document_record(self, document: DocumentRecord) -> DocumentRecord:
        if document.processing_status == "failed":
            document.document_signals = self._coerce_document_signals(document.document_signals)
            document.processing_stage = "failed"
            return document

        if document.processing_status == "processed":
            document.document_signals = self._coerce_document_signals(document.document_signals)
            if not document.processing_stage or document.processing_stage == "queued":
                document.processing_stage = "completed"
            if not document.ocr_status:
                document.ocr_status = "not_needed"
            if document.ocr_status != "used":
                document.ocr_engine = None
            self._normalize_legacy_pdf_ocr_state(document)
            return document

        if document.processing_stage == "completed":
            document.processing_status = "processed"
            return document

        if document.indexing_status in {"indexed", "failed", "skipped"}:
            document.document_signals = self._coerce_document_signals(document.document_signals)
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
        path.write_text(text, encoding="utf-8")

    def _write_chunks(
        self, document_id: str, chunks: list[dict[str, str | int]]
    ) -> None:
        path = self.chunks_dir / f"{document_id}.json"
        with path.open("w", encoding="utf-8") as file_handle:
            json.dump(chunks, file_handle, ensure_ascii=True, indent=2)

    def _remove_processing_artifacts(self, document_id: str) -> None:
        extracted_path = self.extracted_text_dir / f"{document_id}.txt"
        chunks_path = self.chunks_dir / f"{document_id}.json"

        if extracted_path.exists():
            extracted_path.unlink()

        if chunks_path.exists():
            chunks_path.unlink()

    def _metadata_path(self, document_id: str) -> Path:
        return self.metadata_dir / f"{document_id}.json"

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
        raw_terms = re.findall(r"[A-Za-z0-9]{3,}", query.lower())
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
        return [term for term in raw_terms if term not in ignored_terms]

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
        shared_theme = ", ".join(shared_terms[:3]) if shared_terms else "overall topic"
        lead = (
            f"The closest thematic match to {target_document.original_name} is "
            f"{strongest_document.original_name}."
        )
        detail = (
            f" They overlap around {shared_theme}, with an estimated semantic similarity "
            f"of about {round(strongest_score * 100)}%."
        )
        return lead + detail

    def _build_document_similarity_profile(self, document: DocumentRecord) -> str:
        parts = [
            f"name: {document.original_name}",
            f"type: {document.detected_document_type or 'document'}",
        ]
        if document.document_title:
            parts.append(f"title: {document.document_title}")
        if document.document_date:
            parts.append(f"date: {document.document_date}")
        if document.document_entities:
            parts.append(
                "entities: " + ", ".join(document.document_entities[:5])
            )

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

        extracted_path = self.extracted_text_dir / f"{document.id}.txt"
        if extracted_path.exists():
            sample = extracted_path.read_text(encoding="utf-8")[:1200]
            parts.append("sample: " + self._normalize_text_fragment(sample))

        return "\n".join(parts)

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
