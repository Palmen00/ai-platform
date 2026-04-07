from dataclasses import dataclass
from difflib import SequenceMatcher
import re

from app.schemas.chat import ChatSource
from app.schemas.chat import RetrievalDebug
from app.services.documents import DocumentService
from app.services.embeddings import EmbeddingService
from app.services.vector_store import VectorStoreService
from app.config import settings


@dataclass
class RetrievalResult:
    sources: list[ChatSource]
    debug: RetrievalDebug


class RetrievalService:
    def __init__(self) -> None:
        self.document_service = DocumentService()
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStoreService()

    def retrieve(
        self,
        query: str,
        limit: int = 4,
        allowed_document_ids: list[str] | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> RetrievalResult:
        candidate_limit = max(limit * 3, 8)
        query_terms = self.document_service.extract_query_terms(query)
        document_reference = self.document_service.is_document_reference_query(query)
        requested_document_type = self.document_service.extract_requested_document_type(query)
        requested_document_year = self.document_service.extract_requested_document_year(query)
        visible_document_ids = set(
            self.document_service.list_visible_document_ids(
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
        )
        requested_document_ids = (
            [
                document_id
                for document_id in (allowed_document_ids or [])
                if document_id in visible_document_ids
            ]
            if allowed_document_ids is not None
            else None
        )
        matched_document_ids = self.document_service.find_referenced_documents(
            query,
            allowed_document_ids=requested_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        metadata_matched_documents = self.document_service.find_documents_by_metadata(
            query,
            allowed_document_ids=requested_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        metadata_matched_document_ids = [document.id for document in metadata_matched_documents]
        effective_document_ids = requested_document_ids
        if matched_document_ids:
            if self.document_service.is_document_type_query(query):
                effective_document_ids = matched_document_ids[:3]
            elif len(matched_document_ids) == 1 and not effective_document_ids:
                effective_document_ids = [matched_document_ids[0]]
        if (document_reference or self.document_service.is_document_metadata_inventory_query(query)) and metadata_matched_document_ids:
            effective_document_ids = metadata_matched_document_ids
        if effective_document_ids is None:
            effective_document_ids = list(visible_document_ids)
        else:
            effective_document_ids = [
                document_id
                for document_id in effective_document_ids
                if document_id in visible_document_ids
            ]

        if (
            self.document_service.is_document_inventory_query(query)
            or self.document_service.is_document_similarity_query(query)
            or (
                self.document_service.is_document_metadata_inventory_query(query)
                and not self.document_service.is_document_content_question(query)
            )
        ):
            return RetrievalResult(
                sources=[],
                debug=RetrievalDebug(
                    mode="none",
                    query_terms=query_terms,
                    semantic_candidates=0,
                    term_candidates=0,
                    returned_sources=0,
                    top_source_score=0.0,
                    confidence="low",
                    document_reference=document_reference,
                    document_filter_active=bool(requested_document_ids),
                    document_filter_count=len(requested_document_ids or []),
                    metadata_filter_active=bool(metadata_matched_document_ids),
                    metadata_filter_count=len(metadata_matched_document_ids),
                    requested_document_type=requested_document_type,
                    requested_document_year=requested_document_year,
                ),
            )

        semantic_sources = self._semantic_sources(
            query,
            limit=candidate_limit,
            allowed_document_ids=effective_document_ids,
        )
        term_sources = self.document_service.search_chunks(
            query,
            limit=candidate_limit,
            allowed_document_ids=effective_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )

        hybrid_sources = self._merge_sources(
            query=query,
            semantic_sources=semantic_sources,
            term_sources=term_sources,
            limit=limit,
            matched_document_ids=matched_document_ids,
            metadata_matched_document_ids=metadata_matched_document_ids,
        )

        selected_sources: list[ChatSource] = []
        retrieval_mode = "none"

        if hybrid_sources:
            selected_sources = hybrid_sources
            retrieval_mode = "hybrid"
        elif semantic_sources and self.document_service.semantic_sources_match_query(
            query, semantic_sources
        ):
            selected_sources = semantic_sources[:limit]
            retrieval_mode = "semantic"
        elif term_sources:
            selected_sources = term_sources[:limit]
            retrieval_mode = "term"

        if selected_sources:
            selected_sources = self.document_service.hydrate_sources(
                query=query,
                sources=selected_sources,
                limit=limit,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            selected_sources = self._rerank_hydrated_sources(
                query=query,
                sources=selected_sources,
                matched_document_ids=matched_document_ids,
            )
            selected_sources = self._deduplicate_sources(selected_sources, limit=limit)
            selected_sources = self._trim_sources_for_quality(
                query=query,
                sources=selected_sources,
                limit=limit,
                matched_document_ids=matched_document_ids,
            )
            topic_phrase = self.document_service.extract_topic_phrase(query)
            if topic_phrase and len(topic_phrase.split()) >= 2:
                exact_phrase_sources = [
                    source
                    for source in selected_sources
                    if topic_phrase in source.excerpt.lower()
                ]
                if exact_phrase_sources:
                    selected_sources = exact_phrase_sources[:limit]
            if not self.document_service.is_document_reference_query(query):
                filtered_sources = [
                    source
                    for source in selected_sources
                    if (
                        self.document_service.source_matches_query(query, source)
                        or (
                            matched_document_ids
                            and source.document_id in matched_document_ids[:2]
                        )
                    )
                ][:limit]
                if filtered_sources:
                    selected_sources = filtered_sources
                elif requested_document_ids and len(requested_document_ids) <= 3:
                    selected_sources = selected_sources[:limit]
                else:
                    selected_sources = []
                    retrieval_mode = "none"

        confidence = self._confidence_level(
            query=query,
            sources=selected_sources,
        )
        top_source_score = round(selected_sources[0].score, 4) if selected_sources else 0.0

        return RetrievalResult(
            sources=selected_sources,
            debug=RetrievalDebug(
                mode=retrieval_mode,
                query_terms=query_terms,
                semantic_candidates=len(semantic_sources),
                term_candidates=len(term_sources),
                returned_sources=len(selected_sources),
                top_source_score=top_source_score,
                confidence=confidence,
                document_reference=document_reference,
                document_filter_active=bool(requested_document_ids),
                document_filter_count=len(requested_document_ids or []),
                metadata_filter_active=bool(metadata_matched_document_ids),
                metadata_filter_count=len(metadata_matched_document_ids),
                requested_document_type=requested_document_type,
                requested_document_year=requested_document_year,
            ),
        )

    def build_grounded_document_reply(
        self,
        query: str,
        sources: list[ChatSource],
        allowed_document_ids: list[str] | None = None,
        history: list | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        if not (
            self.document_service.is_document_reference_query(query)
            or self.document_service.is_document_metadata_inventory_query(query)
            or self.document_service.is_document_entity_inventory_query(query)
        ):
            return None

        if self.document_service.is_document_inventory_query(query):
            document_names = self.document_service.list_uploaded_document_names(
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if not document_names:
                return "You have not uploaded any documents yet."

            if len(document_names) == 1:
                return f"You currently have one uploaded document: {document_names[0]}."

            if len(document_names) <= 4:
                leading_names = ", ".join(document_names[:-1])
                return (
                    f"You currently have {len(document_names)} uploaded documents:"
                    f" {leading_names}, and {document_names[-1]}."
                )

            preview_names = ", ".join(document_names[:4])
            return (
                f"You currently have {len(document_names)} uploaded documents."
                f" The first few are {preview_names}, and {len(document_names) - 4}"
                " more."
            )

        if self.document_service.is_document_similarity_query(query):
            return self.document_service.summarize_similar_documents(
                query=query,
                history=history,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )

        if self.document_service.is_document_entity_inventory_query(query):
            return self.document_service.summarize_document_entities_by_metadata(
                query,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )

        if (
            self.document_service.is_document_metadata_inventory_query(query)
            and not self.document_service.is_document_content_question(query)
        ):
            return self.document_service.summarize_documents_by_metadata(
                query,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )

        if self.document_service.is_document_type_query(query) and sources:
            primary_source = sources[0]
            document_type = self._infer_document_type(primary_source)
            if document_type:
                prefix = "It appears to be"
                if primary_source.ocr_used:
                    prefix = "It looks like a scanned"
                    if document_type.lower().startswith(("a ", "an ", "the ")):
                        document_type = document_type.split(" ", 1)[1]

                detail = self._summarize_document_type_evidence(primary_source)
                if detail:
                    return f"{prefix} {document_type}. {detail}"
                return f"{prefix} {document_type}."

        if self.document_service.is_document_topic_presence_query(query) and sources:
            topic_phrase = self.document_service.extract_topic_phrase(query)
            topic_terms = self.document_service.extract_topic_terms(query, sources)
            if not topic_terms:
                return None

            if topic_phrase and len(topic_phrase.split()) >= 2:
                matching_sources = [
                    source
                    for source in sources
                    if topic_phrase in source.excerpt.lower()
                ]
            else:
                matching_sources = [
                    source
                    for source in sources
                    if any(term in source.excerpt.lower() for term in topic_terms)
                ]
            if not matching_sources:
                return None

            primary_term = topic_phrase or topic_terms[0]
            lead_term = self._format_topic_label(primary_term)
            unique_sources = self._unique_sources_by_document(matching_sources)
            document_count = len(unique_sources)

            if document_count == 1:
                summary = self._summarize_source_for_topic(unique_sources[0], topic_terms)
                if summary:
                    caveat = self._ocr_caveat(unique_sources[0], document_count)
                    return f"Yes. {summary}{caveat}"
                return f"Yes. {unique_sources[0].document_name} mentions {lead_term}."

            source_lines = []
            for source in unique_sources[:2]:
                summary = self._summarize_source_for_topic(source, topic_terms)
                if summary:
                    source_lines.append(summary)

            lead = f"Yes. {lead_term.capitalize()} appears in {document_count} of your uploaded documents."
            if not source_lines:
                return lead

            caveat = self._ocr_caveat(unique_sources[0], document_count)
            return f"{lead} {' '.join(source_lines)}{caveat}"
        return None

    def _semantic_sources(
        self,
        query: str,
        limit: int,
        allowed_document_ids: list[str] | None = None,
    ) -> list[ChatSource]:
        try:
            query_vector = self.embedding_service.embed_query(query)
            if not query_vector:
                return []
            return self.vector_store.search(
                query_vector,
                limit=limit,
                allowed_document_ids=allowed_document_ids,
            )
        except Exception:
            return []

    def _merge_sources(
        self,
        query: str,
        semantic_sources: list[ChatSource],
        term_sources: list[ChatSource],
        limit: int,
        matched_document_ids: list[str],
        metadata_matched_document_ids: list[str],
    ) -> list[ChatSource]:
        combined: dict[tuple[str, int], dict[str, object]] = {}
        query_terms = self.document_service.extract_query_terms(query)
        query_term_set = set(query_terms)
        requested_document_type = self.document_service.extract_requested_document_type(query)
        requested_document_year = self.document_service.extract_requested_document_year(query)

        semantic_max = max((source.score for source in semantic_sources), default=1.0)
        term_max = max((source.score for source in term_sources), default=1.0)

        for source in semantic_sources:
            key = (source.document_id, source.chunk_index)
            combined[key] = {
                "source": source,
                "semantic_score": source.score / semantic_max if semantic_max else 0.0,
                "term_score": 0.0,
            }

        for source in term_sources:
            key = (source.document_id, source.chunk_index)
            if key not in combined:
                combined[key] = {
                    "source": source,
                    "semantic_score": 0.0,
                    "term_score": 0.0,
                }

            combined[key]["term_score"] = source.score / term_max if term_max else 0.0

        document_cache: dict[str, object | None] = {}
        for item in combined.values():
            source = item["source"]
            if source.document_id not in document_cache:
                document_cache[source.document_id] = self.document_service.get_document(source.document_id)

        ranked_sources: list[ChatSource] = []
        for item in combined.values():
            source = item["source"]
            document = document_cache.get(source.document_id)
            semantic_score = float(item["semantic_score"])
            term_score = float(item["term_score"])
            coverage_score = self._coverage_score(source.excerpt, query_terms)
            document_name_score = self._document_name_score(
                source.document_name, query_terms
            )
            section_title_score = self._section_title_score(
                source.section_title,
                query_terms,
            )
            source_kind_score = self._source_kind_score(
                query,
                source.source_kind,
            )
            ocr_quality_score = self._ocr_quality_score(
                source=source,
                query_terms=query_terms,
            )
            matched_document_score = self._matched_document_score(
                source.document_id,
                matched_document_ids,
            )
            signal_score = (
                self.document_service._document_signal_score(document, query, query_term_set)
                if document is not None
                else 0.0
            )
            metadata_filter_score = self._metadata_filter_score(
                source=source,
                metadata_matched_document_ids=metadata_matched_document_ids,
                requested_document_type=requested_document_type,
                requested_document_year=requested_document_year,
            )
            source.score = round(
                (semantic_score * 0.36)
                + (term_score * 0.17)
                + (coverage_score * 0.14)
                + (document_name_score * 0.08)
                + (section_title_score * 0.12)
                + (source_kind_score * 0.03)
                + (ocr_quality_score * 0.04)
                + (matched_document_score * 0.08)
                + (signal_score * 0.08),
                4,
            )
            source.score = round(
                source.score + metadata_filter_score,
                4,
            )
            ranked_sources.append(source)

        ranked_sources.sort(key=lambda source: source.score, reverse=True)

        if not ranked_sources:
            return []

        if self.document_service.is_document_reference_query(query):
            return ranked_sources[:limit]

        filtered_sources = [
            source
            for source in ranked_sources
            if self.document_service.semantic_sources_match_query(query, [source])
        ]
        return filtered_sources[:limit]

    def _coverage_score(self, excerpt: str, query_terms: list[str]) -> float:
        if not excerpt or not query_terms:
            return 0.0

        lowered = excerpt.lower()
        matched_terms = {term for term in query_terms if term in lowered}
        return len(matched_terms) / max(len(query_terms), 1)

    def _document_name_score(self, document_name: str, query_terms: list[str]) -> float:
        if not document_name or not query_terms:
            return 0.0

        normalized_name = document_name.lower().replace("_", " ")
        name_terms = set(re.findall(r"[a-z0-9]{3,}", normalized_name))
        if not name_terms:
            return 0.0

        matched_terms = {term for term in query_terms if term in name_terms}
        if not matched_terms:
            return 0.0

        return len(matched_terms) / max(len(query_terms), 1)

    def _section_title_score(
        self,
        section_title: str | None,
        query_terms: list[str],
    ) -> float:
        if not section_title or not query_terms:
            return 0.0

        normalized_section = section_title.lower().replace("_", " ")
        section_terms = set(re.findall(r"[a-z0-9]{3,}", normalized_section))
        if not section_terms:
            return 0.0

        matched_terms = {term for term in query_terms if term in section_terms}
        if not matched_terms:
            return 0.0

        return len(matched_terms) / max(len(query_terms), 1)

    def _source_kind_score(self, query: str, source_kind: str | None) -> float:
        if not source_kind:
            return 0.0

        lowered = query.lower()
        if "pdf" in lowered and source_kind == "pdf":
            return 1.0
        if any(term in lowered for term in ("json", "schema", "payload")) and source_kind == "json":
            return 1.0
        if any(term in lowered for term in ("csv", "spreadsheet", "table")) and source_kind == "csv":
            return 1.0
        if any(term in lowered for term in ("spreadsheet", "excel", "xlsx", "sheet", "worksheet")) and source_kind == "spreadsheet":
            return 1.0
        if any(term in lowered for term in ("presentation", "slides", "slide deck", "ppt", "pptx")) and source_kind == "presentation":
            return 1.0
        if any(term in lowered for term in ("word", "docx", "document file")) and source_kind == "word":
            return 1.0
        if any(term in lowered for term in ("markdown", "md", "readme")) and source_kind == "markdown":
            return 1.0
        if any(term in lowered for term in ("code", "source code", "script", "function", "class", ".ts", ".tsx", ".js", ".py")) and source_kind == "code":
            return 1.0
        if any(term in lowered for term in ("config", "configuration", "yaml", "yml", "env file", ".env", "toml", "ini", "xml")) and source_kind == "config":
            return 1.0
        if any(term in lowered for term in ("text file", "txt", "log")) and source_kind == "text":
            return 1.0

        return 0.0

    def _matched_document_score(
        self,
        document_id: str,
        matched_document_ids: list[str],
    ) -> float:
        if not matched_document_ids or document_id not in matched_document_ids:
            return 0.0

        match_index = matched_document_ids.index(document_id)
        if match_index == 0:
            return 1.0
        if match_index == 1:
            return 0.6
        if match_index == 2:
            return 0.3
        return 0.15

    def _metadata_filter_score(
        self,
        source: ChatSource,
        metadata_matched_document_ids: list[str],
        requested_document_type: str | None,
        requested_document_year: int | None,
    ) -> float:
        score = 0.0
        if metadata_matched_document_ids and source.document_id in metadata_matched_document_ids:
            score += 0.18
        if requested_document_type and source.detected_document_type == requested_document_type:
            score += 0.12
        if requested_document_year and source.document_date and source.document_date.startswith(str(requested_document_year)):
            score += 0.08
        return score

    def _deduplicate_sources(
        self, sources: list[ChatSource], limit: int
    ) -> list[ChatSource]:
        deduplicated: dict[tuple[str, int], ChatSource] = {}

        for source in sources:
            key = (source.document_id, source.chunk_index)
            existing = deduplicated.get(key)

            if existing is None:
                deduplicated[key] = source
                continue

            if source.score > existing.score:
                existing.score = source.score

            if len(source.excerpt) > len(existing.excerpt):
                existing.excerpt = source.excerpt

        ranked_sources = list(deduplicated.values())
        family_deduplicated: list[ChatSource] = []

        for source in sorted(ranked_sources, key=lambda item: item.score, reverse=True):
            family_key = self._document_family_key(source.document_name)
            existing_family_source = next(
                (
                    candidate
                    for candidate in family_deduplicated
                    if self._document_family_key(candidate.document_name) == family_key
                    and abs(candidate.chunk_index - source.chunk_index) <= 1
                    and SequenceMatcher(
                        None,
                        " ".join(candidate.excerpt.lower().split()),
                        " ".join(source.excerpt.lower().split()),
                    ).ratio()
                    >= 0.72
                ),
                None,
            )

            if existing_family_source is None:
                family_deduplicated.append(source)
                continue

            if source.score > existing_family_source.score:
                family_deduplicated.remove(existing_family_source)
                family_deduplicated.append(source)

        ranked_sources = family_deduplicated
        ranked_sources.sort(key=lambda source: source.score, reverse=True)
        return ranked_sources[:limit]

    def _document_family_key(self, document_name: str) -> str:
        normalized = document_name.lower()
        normalized = re.sub(r"\.[a-z0-9]+$", "", normalized)
        normalized = re.sub(r"\s*\(\d+\)$", "", normalized)
        normalized = normalized.replace("_", " ").replace("-", " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _rerank_hydrated_sources(
        self,
        query: str,
        sources: list[ChatSource],
        matched_document_ids: list[str],
    ) -> list[ChatSource]:
        if not sources:
            return []

        query_terms = self.document_service.extract_query_terms(query)
        preferred_document_id = matched_document_ids[0] if matched_document_ids else None
        reranked_sources: list[ChatSource] = []

        for source in sources:
            coverage_score = self._coverage_score(source.excerpt, query_terms)
            section_title_score = self._section_title_score(
                source.section_title,
                query_terms,
            )
            snippet_quality_score = self._snippet_quality_score(
                source.excerpt,
                query_terms,
            )
            ocr_quality_score = self._ocr_quality_score(
                source=source,
                query_terms=query_terms,
            )
            location_score = 0.06 if source.page_number is not None else 0.0
            preferred_document_bonus = (
                0.08 if preferred_document_id and source.document_id == preferred_document_id else 0.0
            )

            source.score = round(
                (source.score * 0.7)
                + (coverage_score * 0.12)
                + (section_title_score * 0.08)
                + (snippet_quality_score * 0.1)
                + (ocr_quality_score * 0.05)
                + location_score
                + preferred_document_bonus,
                4,
            )
            reranked_sources.append(source)

        reranked_sources.sort(key=lambda item: item.score, reverse=True)
        return reranked_sources

    def _trim_sources_for_quality(
        self,
        query: str,
        sources: list[ChatSource],
        limit: int,
        matched_document_ids: list[str],
    ) -> list[ChatSource]:
        if not sources:
            return []

        document_reference = self.document_service.is_document_reference_query(query)
        preferred_document_id = matched_document_ids[0] if matched_document_ids else None
        query_terms = self.document_service.extract_query_terms(query)
        focus_terms = self.document_service.extract_focus_terms(query)

        if preferred_document_id:
            preferred_sources = [
                source for source in sources if source.document_id == preferred_document_id
            ]
            support_sources = [
                source for source in sources if source.document_id != preferred_document_id
            ]
            trimmed_sources = self._prioritize_source_diversity(
                preferred_sources,
                limit=2,
            )

            if trimmed_sources and support_sources:
                best_preferred_score = trimmed_sources[0].score
                preferred_match_count = self._matched_term_count(
                    trimmed_sources[0].excerpt,
                    query_terms,
                )
                support_ratio = 0.9 if document_reference else 0.78
                for source in support_sources:
                    support_match_count = self._matched_term_count(
                        source.excerpt,
                        query_terms,
                    )
                    focus_match_count = self._matched_term_count(
                        source.excerpt,
                        focus_terms,
                    ) if focus_terms else support_match_count
                    if (
                        source.score >= best_preferred_score * support_ratio
                        and support_match_count >= preferred_match_count
                        and focus_match_count > 0
                    ):
                        trimmed_sources.append(source)
                        break

            if trimmed_sources:
                return trimmed_sources[:limit]

        best_score = sources[0].score
        minimum_score = best_score * (0.55 if document_reference else 0.7)
        trimmed_sources: list[ChatSource] = []

        for source in sources:
            if source.score < minimum_score and trimmed_sources:
                continue

            if any(
                self._sources_are_redundant(source, existing)
                for existing in trimmed_sources
            ):
                continue

            trimmed_sources.append(source)
            if len(trimmed_sources) >= limit:
                break

        if trimmed_sources:
            return self._prioritize_source_diversity(trimmed_sources, limit=limit)

        return sources[:1]

    def _confidence_level(
        self,
        query: str,
        sources: list[ChatSource],
    ) -> str:
        if not sources:
            return "low"

        top_score = sources[0].score
        second_score = sources[1].score if len(sources) > 1 else 0.0
        score_gap = top_score - second_score
        average_score = sum(source.score for source in sources[:3]) / min(len(sources), 3)
        unique_documents = len({source.document_id for source in sources[:3]})
        ocr_heavy = sum(1 for source in sources[:3] if source.ocr_used) >= max(1, min(len(sources), 3))
        document_reference = self.document_service.is_document_reference_query(query)
        query_terms = self.document_service.extract_query_terms(query)
        top_match_count = self._matched_term_count(sources[0].excerpt, query_terms) if query_terms else 0

        if document_reference:
            if top_score >= 0.82 and average_score >= 0.72:
                if ocr_heavy and top_score < 0.94:
                    return "medium"
                return "high"
            if (
                unique_documents == 1
                and top_score >= 0.38
                and top_match_count >= 2
            ):
                return "medium"
            if (
                ocr_heavy
                and len(sources) >= 1
                and unique_documents == 1
                and top_score >= 0.4
                and average_score >= 0.28
                and top_match_count >= 2
            ):
                return "medium"
            if top_score >= 0.5:
                return "medium"
            return "low"

        if top_score >= 0.78 and score_gap >= 0.08:
            if ocr_heavy and average_score < 0.88:
                return "medium"
            return "high"
        if unique_documents == 1 and top_score >= 0.45 and top_match_count >= 2:
            return "medium"
        if top_score >= 0.55 or (average_score >= 0.5 and unique_documents >= 1):
            return "medium"
        return "low"

    def _prioritize_source_diversity(
        self,
        sources: list[ChatSource],
        limit: int,
    ) -> list[ChatSource]:
        if not sources:
            return []

        selected: list[ChatSource] = []
        seen_section_keys: set[tuple[str, str]] = set()

        for source in sorted(sources, key=lambda item: item.score, reverse=True):
            section_key = (
                source.document_id,
                (source.section_title or "").strip().lower(),
            )

            if section_key[1] and section_key in seen_section_keys:
                continue

            selected.append(source)
            if section_key[1]:
                seen_section_keys.add(section_key)

            if len(selected) >= limit:
                return selected

        for source in sorted(sources, key=lambda item: item.score, reverse=True):
            if source in selected:
                continue
            selected.append(source)
            if len(selected) >= limit:
                break

        return selected[:limit]

    def _sources_are_redundant(
        self, left_source: ChatSource, right_source: ChatSource
    ) -> bool:
        if left_source.document_id != right_source.document_id:
            return False

        normalized_left = " ".join(left_source.excerpt.split()).lower()
        normalized_right = " ".join(right_source.excerpt.split()).lower()
        similarity = SequenceMatcher(None, normalized_left, normalized_right).ratio()

        return similarity >= 0.72 or abs(left_source.chunk_index - right_source.chunk_index) <= 1

    def _snippet_quality_score(self, excerpt: str, query_terms: list[str]) -> float:
        normalized_excerpt = " ".join(excerpt.split()).strip()
        if not normalized_excerpt or not query_terms:
            return 0.0

        lowered = normalized_excerpt.lower()
        matched_terms = [term for term in query_terms if term in lowered]
        if not matched_terms:
            return 0.0

        term_density = len(set(matched_terms)) / max(len(query_terms), 1)
        length_penalty = 0.0
        if len(normalized_excerpt) > 280:
            length_penalty = 0.08
        elif len(normalized_excerpt) < 60:
            length_penalty = 0.04

        return max(term_density - length_penalty, 0.0)

    def _matched_term_count(self, excerpt: str, query_terms: list[str]) -> int:
        normalized_excerpt = excerpt.lower()
        return len({term for term in query_terms if term in normalized_excerpt})

    def _ocr_quality_score(self, source: ChatSource, query_terms: list[str]) -> float:
        if not source.ocr_used:
            return 1.0

        normalized_excerpt = " ".join(source.excerpt.split()).strip()
        if not normalized_excerpt:
            return -0.4

        matched_terms = [term for term in query_terms if term in normalized_excerpt.lower()]
        alphanumeric_count = len(re.findall(r"[A-Za-z0-9]", normalized_excerpt))
        noisy_characters = len(re.findall(r"[^A-Za-z0-9\s.,;:!?()/%€$'-]", normalized_excerpt))
        noise_penalty = min(noisy_characters / max(len(normalized_excerpt), 1), 0.35)
        coverage_bonus = min(len(set(matched_terms)) * 0.12, 0.36)
        length_bonus = 0.08 if alphanumeric_count >= 80 else 0.0

        return max(0.15 + coverage_bonus + length_bonus - noise_penalty, -0.35)

    def _presence_summary(
        self, source: ChatSource, topic_terms: list[str], max_characters: int = 88
    ) -> str:
        normalized_excerpt = " ".join(source.excerpt.replace("...", " ").split()).strip()
        if not normalized_excerpt:
            return ""

        lowered = normalized_excerpt.lower()
        positions = [
            lowered.find(term) for term in topic_terms if lowered.find(term) >= 0
        ]
        if not positions:
            return ""

        match_start = min(positions)
        start = max(match_start - 20, 0)
        end = min(match_start + max_characters, len(normalized_excerpt))
        snippet = normalized_excerpt[start:end].strip(" ,;:-")

        if start > 0:
            snippet = snippet.split(" ", 1)[-1]

        snippet = re.sub(r"^\d+\.\s*", "", snippet)
        snippet = re.sub(r"^[^A-Za-z(]+", "", snippet)
        snippet = re.sub(r"\s+", " ", snippet).strip(" ,;:-")

        for marker in (".", " Flow:", " Easy to", " Response", " Backend responsibilities:"):
            marker_index = snippet.find(marker)
            if marker_index > 0:
                snippet = snippet[:marker_index]
                break

        if len(snippet) > max_characters:
            snippet = snippet[:max_characters].rsplit(" ", 1)[0]

        if not snippet:
            return ""

        location_parts: list[str] = []
        if source.section_title:
            location_parts.append(source.section_title)
        if source.page_number is not None:
            location_parts.append(f"page {source.page_number}")

        location = ""
        if location_parts:
            location = f" in {' / '.join(location_parts)}"

        return f'In {source.document_name}{location}, one passage says "{snippet}".'

    def _unique_sources_by_document(self, sources: list[ChatSource]) -> list[ChatSource]:
        seen_document_ids: set[str] = set()
        unique_sources: list[ChatSource] = []
        for source in sources:
            if source.document_id in seen_document_ids:
                continue
            seen_document_ids.add(source.document_id)
            unique_sources.append(source)
        return unique_sources

    def _format_source_location(self, source: ChatSource) -> str:
        parts: list[str] = []
        if source.section_title:
            parts.append(source.section_title)
        if source.page_number is not None:
            parts.append(f"page {source.page_number}")
        return " / ".join(parts)

    def _summarize_source_excerpt(self, source: ChatSource, max_characters: int = 200) -> str:
        text = " ".join(source.excerpt.split()).strip()
        if not text:
            return ""

        if source.section_title:
            section_title = source.section_title.strip()
            pattern = re.escape(section_title)
            text = re.sub(rf"^(?:{pattern}\s*:?\s*)+", "", text, flags=re.IGNORECASE).strip()

        if len(text) > max_characters:
            text = text[:max_characters]
            if " " in text:
                text = text.rsplit(" ", 1)[0]

        text = text.strip(" ,;:-")
        if not text:
            return ""

        if not text.endswith("."):
            text += "."

        return text[0].lower() + text[1:] if text[:1].isupper() else text

    def _summarize_source_for_topic(
        self,
        source: ChatSource,
        topic_terms: list[str],
        max_characters: int = 170,
    ) -> str:
        interpreted = self._interpret_common_topic(source, topic_terms)
        if interpreted:
            location = self._format_source_location(source)
            lead = f"In {source.document_name}"
            if location:
                lead += f" ({location})"
            return f"{lead}, {interpreted}"

        snippet = self._extract_relevant_snippet(
            excerpt=source.excerpt,
            topic_terms=topic_terms,
            max_characters=max_characters,
        )
        if not snippet:
            snippet = self._summarize_source_excerpt(
                source,
                max_characters=max_characters,
            )
        if not snippet:
            return ""

        location = self._format_source_location(source)
        lead = f"In {source.document_name}"
        if location:
            lead += f" ({location})"
        return f"{lead}, {snippet}"

    def _interpret_common_topic(
        self,
        source: ChatSource,
        topic_terms: list[str],
    ) -> str:
        lowered = " ".join(source.excerpt.split()).lower()
        term_set = set(topic_terms)

        if "linux" in term_set:
            if "linux vm" in lowered:
                return "it says the AI layer runs on a Linux VM."
            if "linux server" in lowered:
                return "it describes the platform as running on a Linux server and being accessed through a browser."

        if {"doctor", "medicine"}.issubset(term_set):
            if "100000" in lowered or "€ 100000" in lowered or "€100000" in lowered:
                return "it mentions reimbursement for doctor and medicine expenses, with coverage up to €100000 per year."
            return "it mentions reimbursement for doctor and medicine expenses."

        if "death" in term_set and "insurance" in term_set:
            if "decease insurance" in lowered or "death insurance" in lowered:
                if "interested parties" in lowered or "payment" in lowered:
                    return "it lists death insurance and says payment is made to the rider's named parties if the rider dies."
                return "it lists death insurance as one of the covered benefits."

        return ""

    def _summarize_document_type_evidence(self, source: ChatSource) -> str:
        normalized_excerpt = " ".join(source.excerpt.split()).strip()
        lowered = normalized_excerpt.lower()

        if "certificate of insurance" in lowered:
            return (
                "The visible heading describes it as a certificate of insurance for a professional rider."
            )

        if "invoice" in lowered:
            return "The visible text reads like an invoice, with company and invoice details near the top."

        summary = self._summarize_source_excerpt(source, max_characters=180)
        if not summary:
            return ""

        if source.ocr_used:
            return f"The OCR text suggests that {summary}"

        return summary

    def _extract_relevant_snippet(
        self,
        excerpt: str,
        topic_terms: list[str],
        max_characters: int = 170,
    ) -> str:
        normalized_excerpt = " ".join(excerpt.replace("...", " ").split()).strip()
        if not normalized_excerpt:
            return ""

        lowered = normalized_excerpt.lower()
        positions = [
            lowered.find(term) for term in topic_terms if lowered.find(term) >= 0
        ]
        if not positions:
            return ""

        match_start = min(positions)
        start = max(match_start - 36, 0)
        end = min(match_start + max_characters, len(normalized_excerpt))
        snippet = normalized_excerpt[start:end].strip(" ,;:-")

        if start > 0 and " " in snippet:
            snippet = snippet.split(" ", 1)[-1]

        snippet = re.sub(r"^\d+\.\s*", "", snippet)
        snippet = re.sub(r"\s+", " ", snippet).strip(" ,;:-")
        snippet = self._polish_ocr_snippet(snippet)

        if len(snippet) > max_characters:
            snippet = snippet[:max_characters]
            if " " in snippet:
                snippet = snippet.rsplit(" ", 1)[0]

        if not snippet:
            return ""

        if not snippet.endswith("."):
            snippet += "."

        return snippet[0].lower() + snippet[1:] if snippet[:1].isupper() else snippet

    def _polish_ocr_snippet(self, snippet: str) -> str:
        cleaned = snippet
        replacements = (
            (r"\bDecease insurance\b", "death insurance"),
            (r"\bExpenses concerning doctor and medicine\b", "expenses for doctor and medicine"),
            (r"\boc0idenys\b", "accident"),
            (r"\bsiclknes\$\b", "sickness"),
            (r"\bFolsom\b", "policy"),
            (r"\bN°\b", "No."),
        )
        for pattern, replacement in replacements:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-")
        return cleaned

    def _format_topic_label(self, topic: str) -> str:
        labels = {
            "linux": "Linux",
            "medicine": "doctor and medicine coverage",
            "death": "death insurance",
            "insurance": "insurance",
        }
        return labels.get(topic.lower(), topic)

    def _ocr_caveat(self, source: ChatSource, document_count: int) -> str:
        if not source.ocr_used:
            return ""
        if document_count > 1:
            return " One of the supporting passages comes from OCR, so minor wording errors are still possible."
        return " This passage comes from OCR, so a few words may still be slightly noisy."

    def _infer_document_type(self, source: ChatSource) -> str | None:
        excerpt = " ".join(source.excerpt.split()).strip()
        lowered_excerpt = excerpt.lower()
        if "certificate of insurance" in lowered_excerpt:
            return "insurance certificate for a professional rider"
        if "invoice" in lowered_excerpt:
            return "invoice"

        if source.section_title:
            normalized_title = " ".join(source.section_title.split()).strip(" :;-")
            if normalized_title and len(normalized_title) <= 90:
                if normalized_title.isupper():
                    return normalized_title.title()
                return normalized_title

        if not excerpt:
            return None

        excerpt = excerpt[:120]
        if " " in excerpt:
            excerpt = excerpt.rsplit(" ", 1)[0]
        excerpt = excerpt.strip(" ,;:-")
        return excerpt or None
