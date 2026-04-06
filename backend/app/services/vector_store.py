import time
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.http import models

from app.config import settings
from app.schemas.chat import ChatSource
from app.schemas.document import DocumentRecord
from app.schemas.settings import DependencyStatus


class VectorStoreService:
    def __init__(self) -> None:
        pass

    @property
    def collection_name(self) -> str:
        return settings.qdrant_collection_name

    def _create_client(self) -> QdrantClient:
        return QdrantClient(url=settings.qdrant_url)

    def _call_with_retry(self, operation, *, retry_delay_seconds: float = 0.5):
        last_exception: Exception | None = None

        for attempt in range(2):
            client = self._create_client()
            try:
                return operation(client)
            except Exception as exc:
                last_exception = exc
                if attempt == 0:
                    time.sleep(retry_delay_seconds)
                    continue

        if last_exception is not None:
            raise last_exception

        raise RuntimeError("Qdrant operation failed without an exception.")

    def _collection_exists(self) -> bool:
        return bool(
            self._call_with_retry(
                lambda client: client.collection_exists(self.collection_name)
            )
        )

    def index_document_chunks(
        self,
        document: DocumentRecord,
        chunks: list[dict[str, str | int]],
        embeddings: list[list[float]],
    ) -> None:
        if not chunks or not embeddings:
            return

        vector_size = len(embeddings[0])
        self._ensure_collection(vector_size)

        points = []
        for chunk, embedding in zip(chunks, embeddings, strict=False):
            chunk_index = int(chunk.get("index", 0))
            content = str(chunk.get("content", ""))
            section_title = (
                str(chunk.get("section_title", "")).strip() or None
            )
            page_number = chunk.get("page_number")
            source_kind = str(chunk.get("source_kind", "")).strip() or None
            points.append(
                models.PointStruct(
                    id=str(uuid5(NAMESPACE_URL, f"{document.id}:{chunk_index}")),
                    vector=embedding,
                    payload={
                        "document_id": document.id,
                        "document_name": document.original_name,
                        "chunk_index": chunk_index,
                        "content": content,
                        "section_title": section_title,
                        "page_number": int(page_number) if page_number else None,
                        "source_kind": source_kind,
                        "detected_document_type": document.detected_document_type,
                        "document_entities": document.document_entities,
                        "document_date": document.document_date,
                        "document_date_label": document.document_date_label,
                        "document_date_kind": document.document_date_kind,
                        "ocr_used": bool(document.ocr_used),
                    },
                )
            )

        if points:
            self._call_with_retry(
                lambda client: client.upsert(
                    collection_name=self.collection_name,
                    points=points,
                )
            )

    def remove_document_chunks(self, document_id: str) -> None:
        if not self._collection_exists():
            return

        self._call_with_retry(
            lambda client: client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="document_id",
                                match=models.MatchValue(value=document_id),
                            )
                        ]
                    )
                ),
            ),
        )

    def search(
        self,
        query_vector: list[float],
        limit: int,
        allowed_document_ids: list[str] | None = None,
    ) -> list[ChatSource]:
        if not query_vector:
            return []

        if not self._collection_exists():
            return []

        query_filter = None
        if allowed_document_ids:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id",
                        match=models.MatchAny(any=allowed_document_ids),
                    )
                ]
            )

        results = self._call_with_retry(
            lambda client: client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                with_payload=True,
                query_filter=query_filter,
            )
        )

        sources: list[ChatSource] = []
        for hit in results:
            if float(hit.score) < settings.retrieval_min_score:
                continue

            payload = hit.payload or {}
            sources.append(
                ChatSource(
                    document_id=str(payload.get("document_id", "")),
                    document_name=str(payload.get("document_name", "unknown")),
                    chunk_index=int(payload.get("chunk_index", 0)),
                    score=float(hit.score),
                    excerpt=str(payload.get("content", ""))[:280],
                    section_title=(
                        str(payload.get("section_title", "")).strip() or None
                    ),
                    page_number=(
                        int(payload.get("page_number"))
                        if payload.get("page_number") is not None
                        else None
                    ),
                    source_kind=str(payload.get("source_kind", "")).strip() or None,
                    detected_document_type=(
                        str(payload.get("detected_document_type", "")).strip() or None
                    ),
                    document_date=(
                        str(payload.get("document_date", "")).strip() or None
                    ),
                    document_date_label=(
                        str(payload.get("document_date_label", "")).strip() or None
                    ),
                    ocr_used=bool(payload.get("ocr_used", False)),
                )
            )

        return sources

    def _ensure_collection(self, vector_size: int) -> None:
        if self._collection_exists():
            return

        try:
            self._call_with_retry(
                lambda client: client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )
            )
        except Exception:
            if self._collection_exists():
                return
            raise

    def get_status(self) -> DependencyStatus:
        try:
            collection_exists = self._collection_exists()
            indexed_point_count: int | None = None

            if collection_exists:
                collection_info = self._call_with_retry(
                    lambda client: client.get_collection(self.collection_name)
                )
                indexed_point_count = getattr(
                    collection_info,
                    "points_count",
                    None,
                )

            return DependencyStatus(
                status="ok",
                url=settings.qdrant_url,
                detail="Qdrant reachable.",
                collection_name=self.collection_name,
                collection_exists=collection_exists,
                indexed_point_count=indexed_point_count,
            )
        except Exception as exc:
            return DependencyStatus(
                status="error",
                url=settings.qdrant_url,
                detail=str(exc),
                collection_name=self.collection_name,
                collection_exists=False,
                indexed_point_count=0,
            )
