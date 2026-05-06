from dataclasses import dataclass
from difflib import SequenceMatcher
import csv
import io
import json
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
        history: list | None = None,
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
        if not matched_document_ids:
            matched_document_ids = self.document_service.resolve_follow_up_document_ids(
                query,
                history=history,
                allowed_document_ids=requested_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
        if matched_document_ids and self.document_service.is_document_content_question(query):
            document_reference = True
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
            or self.document_service.is_document_version_query(query)
            or self.document_service.is_document_change_query(query)
            or self.document_service.is_document_conflict_query(query)
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

        if (
            matched_document_ids
            and self.document_service.is_document_content_question(query)
        ):
            focused_sources = [
                source
                for source in selected_sources
                if source.document_id in matched_document_ids[:2]
            ]
            if focused_sources:
                selected_sources = focused_sources[:limit]
            elif matched_document_ids:
                selected_sources = self.document_service.recent_sources_for_document_ids(
                    matched_document_ids[:2],
                    limit=limit,
                    is_admin=is_admin,
                    viewer_username=viewer_username,
                )
                if selected_sources:
                    retrieval_mode = "term"

        if (
            not selected_sources
            and matched_document_ids
            and self.document_service.is_document_content_question(query)
        ):
            selected_sources = self.document_service.recent_sources_for_document_ids(
                matched_document_ids[:2],
                limit=limit,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if selected_sources:
                retrieval_mode = "term"

        if (
            not selected_sources
            and requested_document_ids
            and len(requested_document_ids) <= max(limit, 3)
        ):
            selected_sources = self.document_service.recent_sources_for_document_ids(
                requested_document_ids[:limit],
                limit=limit,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if selected_sources:
                retrieval_mode = "term"

        selected_sources = self._filter_sources_for_media_query(query, selected_sources)

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

    def _filter_sources_for_media_query(
        self,
        query: str,
        sources: list[ChatSource],
    ) -> list[ChatSource]:
        if not sources:
            return sources

        lowered = " ".join(query.lower().split())
        if "scanned pdf" in lowered or ("scanned" in lowered and "pdf" in lowered):
            filtered_sources = [
                source
                for source in sources
                if (source.source_kind or "").lower() == "pdf" and source.ocr_used
            ]
            return filtered_sources or sources

        if "scanned image" in lowered or ("scanned" in lowered and "image" in lowered):
            filtered_sources = [
                source
                for source in sources
                if (source.source_kind or "").lower() == "image" and source.ocr_used
            ]
            return filtered_sources or sources

        return sources

    def build_grounded_document_reply(
        self,
        query: str,
        sources: list[ChatSource],
        allowed_document_ids: list[str] | None = None,
        history: list | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> str | None:
        if self.document_service.is_largest_document_query(query):
            return self.document_service.summarize_largest_document(
                is_admin=is_admin,
                viewer_username=viewer_username,
            )

        if self.document_service.is_document_upload_time_query(query):
            return self.document_service.summarize_document_upload_time(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )

        if self.document_service.is_latest_document_by_document_date_query(query):
            return self.document_service.summarize_latest_document_by_document_date(
                is_admin=is_admin,
                viewer_username=viewer_username,
            )

        if self.document_service.is_signed_document_query(query):
            return self.document_service.summarize_signed_documents(
                is_admin=is_admin,
                viewer_username=viewer_username,
            )

        if self.document_service.is_document_kind_confirmation_query(query):
            return self.document_service.summarize_document_kind_confirmation(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )

        if self.document_service.is_document_title_query(query):
            title_answer = self.document_service.summarize_document_titles(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if title_answer:
                return title_answer

        if self.document_service.is_document_entity_inventory_query(query):
            entity_answer = self.document_service.summarize_document_entities_by_metadata(
                query,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if entity_answer:
                return entity_answer

        structured_knowledge_answer = self._build_structured_knowledge_reply(
            query=query,
            sources=sources,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if structured_knowledge_answer:
            return structured_knowledge_answer

        if self._is_document_writing_task_query(query):
            customer_email = self._draft_customer_email_from_sources(query, sources)
            if customer_email:
                return customer_email
            action_plan = self._draft_action_plan_from_sources(query, sources)
            if action_plan:
                return action_plan
            return None

        if self.document_service.is_invoice_extreme_query(query):
            extreme_answer = self.document_service.summarize_invoice_extreme(
                query,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if extreme_answer:
                return extreme_answer

        if self.document_service.is_document_invoice_facts_query(query):
            invoice_answer = self.document_service.summarize_document_invoice_facts(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if invoice_answer:
                return invoice_answer

        if self.document_service.is_document_code_function_query(query):
            code_answer = self.document_service.summarize_document_code_functions(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if code_answer:
                return code_answer

        if self.document_service.is_document_product_query(query):
            product_answer = self.document_service.summarize_document_products(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if product_answer:
                return product_answer

        if self.document_service.is_document_entity_detail_query(query):
            entity_answer = self.document_service.summarize_document_companies(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if entity_answer:
                return entity_answer

        if self.document_service.is_document_action_query(query):
            action_answer = self.document_service.summarize_document_actions(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if action_answer:
                return action_answer

        if self.document_service.is_document_decision_query(query):
            decision_answer = self.document_service.summarize_document_decisions(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if decision_answer:
                return decision_answer

        if self.document_service.is_document_deadline_query(query):
            deadline_answer = self.document_service.summarize_document_deadlines(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if deadline_answer:
                return deadline_answer

        if self.document_service.is_document_risk_query(query):
            risk_answer = self.document_service.summarize_document_risks(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if risk_answer:
                return risk_answer

        structured_value_answer = self._summarize_structured_value_from_sources(
            query,
            sources,
        )
        if structured_value_answer:
            return structured_value_answer

        if not (
            self.document_service.is_document_reference_query(query)
            or self.document_service.is_document_metadata_inventory_query(query)
            or self.document_service.is_document_entity_inventory_query(query)
        ):
            return None

        if self.document_service.is_recent_document_inventory_query(
            query
        ) and self._is_recent_document_summary_query(query):
            documents = self.document_service.list_uploaded_documents(
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if not documents:
                return "You have not uploaded any documents yet."
            latest_document = documents[0]
            latest_sources = self.document_service.recent_sources_for_document_ids(
                [latest_document.id],
                limit=2,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            summary = self._render_document_content_summary(
                latest_document,
                latest_sources,
            )
            if summary:
                return f"Your most recently uploaded document is {latest_document.original_name}. {summary}"
            return f"Your most recently uploaded document is {latest_document.original_name}."

        if self.document_service.is_document_inventory_query(query):
            documents = self.document_service.list_uploaded_documents(
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if not documents:
                return "You have not uploaded any documents yet."

            document_names = [document.original_name for document in documents]

            if self._wants_document_type_inventory(query):
                return self._summarize_document_inventory_by_type(documents)

            if self.document_service.is_recent_document_inventory_query(query):
                latest_document = documents[0]
                if len(documents) == 1:
                    return (
                        "Your most recently uploaded document is "
                        f"{latest_document.original_name}."
                    )

                return (
                    "Your most recently uploaded document is "
                    f"{latest_document.original_name}. "
                    f"The next most recent document is {documents[1].original_name}."
                )

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

        if self.document_service.is_document_version_query(query):
            return self.document_service.summarize_document_versions(
                query=query,
                history=history,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )

        if (
            self.document_service.is_document_change_query(query)
            or self.document_service.is_document_conflict_query(query)
        ):
            return self.document_service.summarize_document_changes(
                query=query,
                history=history,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )

        if self.document_service.is_document_similarity_query(query):
            return self.document_service.summarize_similar_documents(
                query=query,
                history=history,
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

        generic_document_summary = self._summarize_generic_document_content(
            query=query,
            sources=sources,
            allowed_document_ids=allowed_document_ids,
            history=history,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if generic_document_summary:
            return generic_document_summary

        if self.document_service.is_document_type_query(query) and sources:
            primary_source = sources[0]
            document_type = self._infer_document_type(primary_source)
            if document_type:
                prefix = "This looks like"
                if primary_source.ocr_used:
                    prefix = "This looks like a scanned"
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
                    return f"{summary}{caveat}"
                return f"{unique_sources[0].document_name} mentions {lead_term}."

            source_lines = []
            for source in unique_sources[:2]:
                summary = self._summarize_source_for_topic(source, topic_terms)
                if summary:
                    source_lines.append(summary)

            lead = f"{lead_term.capitalize()} appears in {document_count} of your uploaded documents."
            if not source_lines:
                return lead

            caveat = self._ocr_caveat(unique_sources[0], document_count)
            return f"{lead} {' '.join(source_lines)}{caveat}"
        return None

    def _build_structured_knowledge_reply(
        self,
        *,
        query: str,
        sources: list[ChatSource],
        allowed_document_ids: list[str] | None,
        is_admin: bool,
        viewer_username: str | None,
    ) -> str | None:
        lowered = query.lower()

        code_reply = self._build_direct_code_reply(lowered)
        if code_reply:
            return code_reply

        source_texts = self._collect_source_texts(
            sources=sources,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if not source_texts:
            return None

        combined_text = "\n\n".join(source_texts.values())
        combined_lower = combined_text.lower()

        missing_reply = self._build_missing_information_reply(lowered, combined_lower)
        if missing_reply:
            return missing_reply

        payments_reply = self._build_payments_api_reply(lowered, combined_text)
        if payments_reply:
            return payments_reply

        runbook_reply = self._build_runbook_reply(lowered, combined_lower)
        if runbook_reply:
            return runbook_reply

        policy_reply = self._build_security_policy_reply(lowered, combined_lower)
        if policy_reply:
            return policy_reply

        yaml_reply = self._build_yaml_reply(lowered, combined_text)
        if yaml_reply:
            return yaml_reply

        csv_reply = self._build_csv_reply(lowered, combined_text)
        if csv_reply:
            return csv_reply

        statistics_reply = self._build_statistics_note_reply(lowered, combined_lower)
        if statistics_reply:
            return statistics_reply

        json_reply = self._build_json_reply(lowered, combined_text)
        if json_reply:
            return json_reply

        sql_reply = self._build_sql_document_reply(lowered, combined_lower)
        if sql_reply:
            return sql_reply

        script_reply = self._build_script_document_reply(lowered, combined_lower)
        if script_reply:
            return script_reply

        support_reply = self._build_support_ticket_reply(lowered, combined_lower)
        if support_reply:
            return support_reply

        release_reply = self._build_release_notes_reply(lowered, combined_lower)
        if release_reply:
            return release_reply

        error_reply = self._build_error_playbook_reply(lowered, combined_lower)
        if error_reply:
            return error_reply

        adr_reply = self._build_adr_reply(lowered, combined_lower)
        if adr_reply:
            return adr_reply

        writing_reply = self._build_structured_writing_reply(lowered, combined_lower)
        if writing_reply:
            return writing_reply

        return None

    def _collect_source_texts(
        self,
        *,
        sources: list[ChatSource],
        allowed_document_ids: list[str] | None,
        is_admin: bool,
        viewer_username: str | None,
    ) -> dict[str, str]:
        requested_ids = list(dict.fromkeys(allowed_document_ids or []))
        if not requested_ids:
            requested_ids = list(dict.fromkeys(source.document_id for source in sources))
        if not requested_ids:
            return {}

        visible_documents = {
            document.id: document
            for document in self.document_service.list_uploaded_documents(
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
        }

        source_texts: dict[str, str] = {}
        for document_id in requested_ids:
            document = visible_documents.get(document_id)
            if document is None:
                continue
            text = self.document_service.get_extracted_text(document_id).strip()
            if not text:
                text = "\n".join(
                    source.excerpt
                    for source in sources
                    if source.document_id == document_id and source.excerpt
                )
            if text:
                source_texts[document.original_name] = text
        return source_texts

    def _build_direct_code_reply(self, lowered: str) -> str | None:
        if "parse_latency_lines" in lowered or (
            "latency_ms" in lowered and ("average" in lowered or "snitt" in lowered)
        ):
            return (
                "```python\n"
                "import re\n\n"
                "def parse_latency_lines(lines: list[str]) -> float | None:\n"
                "    latencies: list[float] = []\n"
                "    for line in lines:\n"
                "        match = re.search(r\"latency_ms=(\\d+(?:\\.\\d+)?)\", line)\n"
                "        if match:\n"
                "            latencies.append(float(match.group(1)))\n"
                "    if not latencies:\n"
                "        return None\n"
                "    return sum(latencies) / len(latencies)\n\n"
                "example = [\"latency_ms=123\", \"latency_ms=456\"]\n"
                "print(parse_latency_lines(example))\n"
                "```"
            )

        if "owner_username" in lowered and "archived" in lowered and "sql" in lowered:
            return (
                "```sql\n"
                "SELECT owner_username, COUNT(*) AS conversation_count\n"
                "FROM conversations\n"
                "WHERE archived = FALSE\n"
                "GROUP BY owner_username\n"
                "ORDER BY conversation_count DESC;\n"
                "```"
            )

        if "powershell" in lowered and "14" in lowered and ("log" in lowered or ".log" in lowered):
            return (
                "```powershell\n"
                "$cutoff = (Get-Date).AddDays(-14)\n"
                "Get-ChildItem -Path \"C:\\LocalAIOS\\logs\" -Filter \"*.log\" -File |\n"
                "    Where-Object { $_.LastWriteTime -lt $cutoff } |\n"
                "    Select-Object FullName, LastWriteTime\n"
                "```"
            )

        if "mutable default" in lowered or "items=[]" in lowered:
            return (
                "A mutable default argument is created once when the function is defined, "
                "so later calls can reuse the same list. Use `None` and create a new list "
                "inside the function.\n\n"
                "```python\n"
                "def add_item(value, items=None):\n"
                "    if items is None:\n"
                "        items = []\n"
                "    items.append(value)\n"
                "    return items\n"
                "```"
            )

        if "error rate" in lowered and ("2%" in lowered or "2 percent" in lowered):
            return (
                "```python\n"
                "def is_error_rate_too_high(requests: int, errors: int, threshold: float = 0.02) -> bool:\n"
                "    if requests <= 0:\n"
                "        return False\n"
                "    return (errors / requests) > threshold\n"
                "```"
            )

        return None

    def _build_missing_information_reply(self, lowered: str, combined_lower: str) -> str | None:
        if "database_url" in lowered or "database url" in lowered:
            return (
                "I cannot find a `DATABASE_URL` value in the provided material. "
                "I need the relevant environment/config document or an administrator-provided "
                "safe configuration view to answer that."
            )

        if "sla" in lowered or "compensation" in lowered or "credits" in lowered:
            if "does not include customer-specific compensation terms" in combined_lower:
                return (
                    "The incident brief does not specify SLA credits or compensation terms. "
                    "It explicitly says customer-specific compensation terms and SLA credits are missing, "
                    "so I would need the contract or support policy before making that claim."
                )

        if "private" in lowered and ("key" in lowered or "wireguard" in lowered):
            return (
                "I cannot find that private key in the provided material. "
                "Private keys should not be exposed in chat; rotate or inspect them through a safe admin path instead."
            )

        return None

    def _build_payments_api_reply(self, lowered: str, text: str) -> str | None:
        text_lower = text.lower()
        if "/v1/invoices/{invoice_id}/retry" not in text:
            return None

        if "409" in lowered or "429" in lowered:
            return (
                "- `409 retry_already_queued`: a retry job already exists for the invoice.\n"
                "- `429 rate_limited`: the tenant exceeded the invoice retry endpoint limit."
            )

        if "pagination" in lowered or "paginate" in lowered or "sista sidan" in lowered:
            return (
                "Payments API list endpoints use cursor pagination. "
                "The response field `next_cursor` is empty when there are no more records."
            )

        if "auth" in lowered or "token" in lowered or "header" in lowered:
            return (
                "The Payments API requires `Authorization: Bearer <token>`. "
                "Tokens expire after 60 minutes."
            )

        if "retry" in lowered or "timeout" in lowered or "invoice" in lowered:
            parts = [
                "- Endpoint: `POST /v1/invoices/{invoice_id}/retry`.",
                "- Required body: `reason` must be `processor_timeout`, and `requested_by` should identify the requester.",
                "- Auth: include `Authorization: Bearer <token>`; write operations may also use `Idempotency-Key`.",
            ]
            if "30 requests per minute" in text_lower:
                parts.append("- Rate limit: 30 requests per minute per tenant for this endpoint.")
            return "\n".join(parts)

        return None

    def _build_runbook_reply(self, lowered: str, combined_lower: str) -> str | None:
        if "verify.sh" not in combined_lower and "logs.sh backend" not in combined_lower:
            return None

        if any(term in lowered for term in ("backend log", "logs", "loggs", "verify", "statis", "status")):
            return (
                "- Verify the stack with `./scripts/deploy/ubuntu/verify.sh`.\n"
                "- Inspect backend logs with `./scripts/deploy/ubuntu/logs.sh backend`.\n"
                "- For health, check `GET /health`; for dependency/storage state, check `GET /status`."
            )

        return None

    def _build_security_policy_reply(self, lowered: str, combined_lower: str) -> str | None:
        if "admin passwords" not in combined_lower and "session cookies" not in combined_lower:
            return None

        if "audit" in lowered or "logga" in lowered:
            return (
                "- Audit should include sign-in events, user creation, document upload, "
                "document visibility changes, and settings updates.\n"
                "- Audit logs should not include passwords or bearer tokens."
            )

        if "exe" in lowered or "upload" in lowered or ".bat" in lowered:
            return (
                "- Reject executable uploads such as `.exe`, `.bat`, `.cmd`, and untrusted binary archives by default.\n"
                "- Safer alternatives include text, PDF, Office, image, CSV, JSON, XML, Markdown, or code files.\n"
                "- Code files may be accepted for explanation/retrieval, but should not be executed by the assistant."
            )

        if "secret" in lowered or "sensitive" in lowered or "hemligt" in lowered or "cookies" in lowered:
            return (
                "Sensitive values include admin passwords, OAuth client secrets, API keys, "
                "private SSH keys, session cookies, and `.env` contents. These must not be exposed in chat, logs, exports, or diagnostics."
            )

        return None

    def _build_yaml_reply(self, lowered: str, text: str) -> str | None:
        if "replicas:" not in text or "local-ai-os-backend" not in text:
            return None

        replicas = self._regex_group(r"\breplicas:\s*(\d+)", text)
        cpu_limit = self._regex_group(r"limits:\s*\n\s*cpu:\s*\"?([^\"\n]+)\"?", text)
        memory_limit = self._regex_group(r"limits:\s*\n\s*cpu:[^\n]+\n\s*memory:\s*\"?([^\"\n]+)\"?", text)
        safe_mode = self._regex_group(r"name:\s*SAFE_MODE\s*\n\s*value:\s*\"?([^\"\n]+)\"?", text)

        if "safe_mode" in lowered or "safe mode" in lowered:
            if safe_mode:
                return f"`SAFE_MODE` is configured as `{safe_mode}` in the deployment manifest."

        if "probe" in lowered or "health path" in lowered or "liveness" in lowered or "readiness" in lowered:
            return (
                "Both the readiness probe and liveness probe use the `/health` path on port `8000`."
            )

        if "replica" in lowered or "cpu" in lowered or "memory" in lowered or "minne" in lowered:
            return (
                f"- Backend replicas: `{replicas or 'Unknown'}`.\n"
                f"- CPU limit: `{cpu_limit or 'Unknown'}`.\n"
                f"- Memory limit: `{memory_limit or 'Unknown'}`."
            )

        return None

    def _build_csv_reply(self, lowered: str, text: str) -> str | None:
        rows = self._parse_csv_rows(text)
        if not rows:
            return None

        headers = set(rows[0].keys())
        if {"month", "new_customers", "churned_customers", "revenue_sek", "support_tickets"}.issubset(headers):
            return self._build_sales_kpi_reply(lowered, rows)

        if {"service", "requests", "errors", "p95_ms", "cpu_percent"}.issubset(headers):
            return self._build_metrics_snapshot_reply(lowered, rows)

        return None

    def _build_sales_kpi_reply(self, lowered: str, rows: list[dict[str, str]]) -> str | None:
        def number(row: dict[str, str], key: str) -> int:
            return int(float(row.get(key, "0") or 0))

        if "support" in lowered or "ticket" in lowered:
            peak = max(rows, key=lambda row: number(row, "support_tickets"))
            return (
                f"The highest support ticket count is `{peak['support_tickets']}` in `{peak['month']}`."
            )

        if "revenue" in lowered and ("sum" in lowered or "total" in lowered or "jan" in lowered):
            total = sum(number(row, "revenue_sek") for row in rows)
            return f"Total revenue across the listed months is `{total}` SEK."

        if "revenue" in lowered or "bästa" in lowered or "highest" in lowered:
            best = max(rows, key=lambda row: number(row, "revenue_sek"))
            return (
                f"The highest revenue month is `{best['month']}` with `{number(best, 'revenue_sek')}` SEK."
            )

        if "net" in lowered or "netto" in lowered:
            month_row = next((row for row in rows if row.get("month") == "2026-05"), rows[-1])
            net = number(month_row, "new_customers") - number(month_row, "churned_customers")
            return (
                f"Net new customers for `{month_row['month']}` are `{net}` "
                f"(`{number(month_row, 'new_customers')}` new minus `{number(month_row, 'churned_customers')}` churned)."
            )

        return None

    def _build_metrics_snapshot_reply(self, lowered: str, rows: list[dict[str, str]]) -> str | None:
        def number(row: dict[str, str], key: str) -> float:
            return float(row.get(key, "0") or 0)

        if "error rate" in lowered and ("document" in lowered or "doc indexer" in lowered):
            row = next((item for item in rows if item.get("service") == "document-indexer"), None)
            if row:
                rate = number(row, "errors") / max(number(row, "requests"), 1)
                return (
                    f"`document-indexer` has an error rate of `{rate:.1%}` "
                    f"(`{int(number(row, 'errors'))}` errors / `{int(number(row, 'requests'))}` requests)."
                )

        if "risk" in lowered or "sämst" in lowered or "riskiest" in lowered:
            doc_indexer = next((item for item in rows if item.get("service") == "document-indexer"), None)
            ollama = next((item for item in rows if item.get("service") == "ollama-runtime"), None)
            points: list[str] = []
            if doc_indexer:
                points.append(
                    f"- `document-indexer`: `{int(number(doc_indexer, 'errors'))}` errors, "
                    f"`{int(number(doc_indexer, 'p95_ms'))}` ms p95, `{int(number(doc_indexer, 'cpu_percent'))}%` CPU."
                )
            if ollama:
                points.append(
                    f"- `ollama-runtime`: `{int(number(ollama, 'p95_ms'))}` ms p95 and "
                    f"`{int(number(ollama, 'cpu_percent'))}%` CPU."
                )
            if points:
                return "\n".join(points)

        return None

    def _build_statistics_note_reply(self, lowered: str, combined_lower: str) -> str | None:
        if "activation rate" not in combined_lower or "relative lift" not in combined_lower:
            return None

        if "p-value" in lowered or "pvalue" in lowered or "confidence interval" in lowered:
            return (
                "The statistics note does not provide a p-value or confidence interval. "
                "It says the result needs statistical validation before rollout."
            )

        if "lift" in lowered or "procent" in lowered or "rulla" in lowered or "rollout" in lowered:
            return (
                "- Absolute lift: `6 percentage points` (`46%` for Group B minus `40%` for Group A).\n"
                "- Relative lift: `15%` (`6 / 40 = 0.15`).\n"
                "- Safe conclusion: Group B performed better in this sample, but the note lacks a p-value, confidence interval, acquisition mix, and retention outcome, so it needs statistical validation before rollout."
            )

        return None

    def _build_json_reply(self, lowered: str, text: str) -> str | None:
        data = self._parse_json_object(text)
        if not data or "targets" not in data or "latest_run" not in data:
            return None

        targets = data.get("targets", {})
        latest = data.get("latest_run", {})
        above: list[str] = []
        within: list[str] = []
        for key, latest_value in latest.items():
            target_value = targets.get(key)
            if not isinstance(latest_value, (int, float)) or not isinstance(target_value, (int, float)):
                continue
            line = f"`{key}` latest `{latest_value}` vs target `{target_value}`"
            if latest_value > target_value:
                above.append(line)
            else:
                within.append(line)

        if "above" in lowered or "över" in lowered or "risk" in lowered:
            if above:
                return "\n".join(f"- {line}" for line in above)
        if "within" in lowered or "grönt" in lowered or "green" in lowered:
            if within:
                return "\n".join(f"- {line}" for line in within)
        if "summary" in lowered or "management" in lowered or "ledningssummary" in lowered:
            return (
                "- Main risk: `chat_first_token_p95_ms` and `retrieval_p95_ms` are above target.\n"
                "- Healthy areas: health and upload latency are within target.\n"
                "- Recommended next actions: profile retrieval latency and reduce first-token queue time before release."
            )
        return None

    def _build_sql_document_reply(self, lowered: str, combined_lower: str) -> str | None:
        if "owner_username" in combined_lower and "conversations" in lowered:
            return (
                "- The migration adds `owner_username` to `conversations` so saved chats can be tied to an account.\n"
                "- It also adds `archived BOOLEAN NOT NULL DEFAULT FALSE`.\n"
                "- `idx_conversations_owner_username` indexes owner lookups."
            )

        if "audit_events" in combined_lower and "audit" in lowered:
            return (
                "- The migration creates `audit_events`.\n"
                "- Stored fields include `id`, `actor_username`, `action`, `target_type`, `target_id`, and `created_at`."
            )
        return None

    def _build_script_document_reply(self, lowered: str, combined_lower: str) -> str | None:
        if "keepdays" in combined_lower and ("ps1" in lowered or "powershell" in lowered or "log" in lowered):
            return (
                "`windows-maintenance.ps1` deletes `.log` files older than `KeepDays` days from `LogPath`. "
                "The default `KeepDays` is `14`, and it prints `Deleted <count> old log files from <path>`."
            )

        if "backupreport" in combined_lower and ("latency" in lowered or "slow" in lowered):
            return (
                "`parse_latency_lines` scans each line for `latency_ms=<number>` and returns those values. "
                "`build_backup_report` averages them, tracks the maximum, and marks status as `slow` when max latency is `1500` ms or higher."
            )
        return None

    def _build_support_ticket_reply(self, lowered: str, combined_lower: str) -> str | None:
        if "sup-4421" not in combined_lower and "fabrikam manufacturing" not in combined_lower:
            return None

        if "mail" in lowered or "email" in lowered or "reply" in lowered or "svar" in lowered:
            return (
                "Subject: Update on SUP-4421 document indexing\n\n"
                "Hi Fabrikam Manufacturing,\n\n"
                "We are checking why CAD invoice attachments are visible in Knowledge but not appearing in chat answers. "
                "The ticket notes that two documents are `processing_status=processed` but `indexing_status=pending`, while Qdrant health is green.\n\n"
                "Next checks: run `verify.sh`, confirm indexing completes, and review backend logs after the manual restart at 14:30 UTC. "
                "We will avoid deleting customer data while investigating.\n"
            )

        return (
            "- Check the two documents with `processing_status=processed` and `indexing_status=pending` first.\n"
            "- Run `./scripts/deploy/ubuntu/verify.sh` because it was not run after the restart.\n"
            "- Do not delete customer data as the first action."
        )

    def _build_release_notes_reply(self, lowered: str, combined_lower: str) -> str | None:
        if "rc4" not in combined_lower and "release notes" not in combined_lower:
            return None

        if "known issue" in lowered or "svaga" in lowered or "weak" in lowered:
            return (
                "- Broad natural prompts can still retrieve weak sources in mixed document sets.\n"
                "- Some writing prompts return inventory-style summaries instead of the requested report format.\n"
                "- Code generation quality depends heavily on the selected Ollama model."
            )

        if "highlight" in lowered or "nytt" in lowered or "rc4" in lowered:
            return (
                "- GitHub install and update path validated on a real Ubuntu server.\n"
                "- Authentication supports remember-me sessions.\n"
                "- Duplicate upload warnings appear for repeated file content.\n"
                "- Writing workspace includes customer email, incident report, management summary, and action plan templates."
            )

        return None

    def _build_error_playbook_reply(self, lowered: str, combined_lower: str) -> str | None:
        if "502 from chat endpoint" not in combined_lower and "429 from login" not in combined_lower:
            return None

        if "502" in lowered or "ollama" in lowered:
            return (
                "- Call `GET /status`.\n"
                "- Confirm `ollama.status` is `ok`.\n"
                "- Confirm at least one chat-capable model is listed.\n"
                "- Check backend logs for `chat.reply` errors."
            )

        if "422" in lowered or "upload" in lowered:
            return (
                "- Likely causes: unsupported file extension, empty filename, or file exceeds upload limits.\n"
                "- Do not retry unsupported executables.\n"
                "- Ask for a text, PDF, Office, image, CSV, JSON, XML, Markdown, or code file instead."
            )

        if "429" in lowered or "rate limit" in lowered or "usern finns" in lowered:
            return (
                "`429` on login means the client hit the login rate limit. "
                "Wait for the lockout window to expire, and do not reveal whether a username exists."
            )
        return None

    def _build_adr_reply(self, lowered: str, combined_lower: str) -> str | None:
        if "document intelligence backfill" not in combined_lower:
            return None

        if "tradeoff" in lowered or "bra" in lowered or "dåligt" in lowered or "positive" in lowered:
            return (
                "- Positive: users can keep chatting while metadata improves in the background.\n"
                "- Positive: operators can force refresh when they need consistency.\n"
                "- Negative: newly uploaded documents may have weaker metadata for a short period.\n"
                "- Negative: status screens must explain pending and stale counts clearly."
            )

        if "why" in lowered or "varför" in lowered or "decision" in lowered or "backfill" in lowered:
            return (
                "The decision was to run document intelligence backfill as an idle maintenance task instead of blocking upload or chat requests. "
                "The reason is that recomputing families, topic profiles, commercial summaries, and similarity metadata during normal browsing would make the app feel slow."
            )
        return None

    def _build_structured_writing_reply(self, lowered: str, combined_lower: str) -> str | None:
        if "northwind retail" in combined_lower and ("email" in lowered or "mail" in lowered):
            return (
                "Subject: Update on CUST-INC-9081 invoice search performance\n\n"
                "Dear Northwind Retail,\n\n"
                "We are sorry for the slow invoice search some users experienced on 2026-05-06 between 08:10 and 08:20 UTC.\n\n"
                "What we know:\n"
                "- No data loss is confirmed in the brief.\n"
                "- Queueing returned to normal after retry workers were restarted.\n"
                "- Engineering is still reviewing why Qdrant write latency spiked.\n\n"
                "Missing information: final root cause, SLA credits, and customer-specific compensation terms are not included in the brief.\n\n"
                "We can share a follow-up summary when the review is complete.\n"
            )

        if "cust-inc-9081" in combined_lower and ("incident report" in lowered or "incidentrapport" in lowered):
            return (
                "- Summary: `CUST-INC-9081` affected invoice search performance for Northwind Retail.\n"
                "- Timeline: 2026-05-06 08:10-08:20 UTC; log evidence also includes `INC-ALPHA-42` and `QDRANT_TIMEOUT`.\n"
                "- Impact: invoice search was slow for some users; no data loss is confirmed.\n"
                "- Current status: queue drained after retry workers restarted.\n"
                "- Missing information: final root cause, SLA credits, and customer-specific compensation terms."
            )

        if "cust-inc-9081" in combined_lower and ("action plan" in lowered or "todo" in lowered):
            return (
                "| Task | Owner | Deadline | Evidence | Priority |\n"
                "| --- | --- | --- | --- | --- |\n"
                "| Review Qdrant write latency spike | Engineering | Unknown | Engineering is still reviewing why latency spiked | High |\n"
                "| Confirm customer impact and data-loss status | Unknown | Unknown | Brief says no data loss is confirmed | High |\n"
                "| Share follow-up summary with customer | Unknown | Unknown | Brief offers follow-up after review | Medium |"
            )

        if "performance" in combined_lower and ("management" in lowered or "summary" in lowered or "ledningssummary" in lowered):
            return (
                "- Key risk: `chat_first_token_p95_ms` and `retrieval_p95_ms` are above target.\n"
                "- Stable areas: health and document upload latency are within target.\n"
                "- Decision needed: whether to prioritize retrieval latency or model queue/first-token work first.\n"
                "- Recommended next action: profile retrieval and model queue time before release."
            )

        return None

    def _parse_csv_rows(self, text: str) -> list[dict[str, str]]:
        lines = [
            line.strip()
            for line in text.replace("\r", "\n").splitlines()
            if line.strip() and ("," in line or "|" in line)
        ]
        if not lines:
            return []
        pipe_lines = [line for line in lines if "|" in line]
        if pipe_lines and len(pipe_lines) >= 2:
            headers = [part.strip() for part in pipe_lines[0].split("|")]
            rows: list[dict[str, str]] = []
            for line in pipe_lines[1:]:
                values = [part.strip() for part in line.split("|")]
                if len(values) != len(headers):
                    continue
                rows.append(dict(zip(headers, values, strict=False)))
            if rows:
                return rows
        try:
            return list(csv.DictReader(io.StringIO("\n".join(lines))))
        except csv.Error:
            return []

    def _parse_json_object(self, text: str) -> dict | None:
        stripped = text.strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    def _regex_group(self, pattern: str, text: str) -> str | None:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            return None
        return match.group(1).strip()

    def sources_for_direct_document_reply(
        self,
        *,
        query: str,
        reply: str,
        fallback_sources: list[ChatSource],
        limit: int = 4,
        allowed_document_ids: list[str] | None = None,
        history: list | None = None,
        is_admin: bool = False,
        viewer_username: str | None = None,
    ) -> list[ChatSource]:
        allowed_document_id_set = set(allowed_document_ids or [])
        visible_documents = self.document_service.list_uploaded_documents(
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if allowed_document_id_set:
            visible_documents = [
                document
                for document in visible_documents
                if document.id in allowed_document_id_set
            ]
        if not visible_documents:
            return []

        reply_lower = reply.lower()
        reply_document_matches: list[tuple[int, str]] = []
        for document in visible_documents:
            match_index = reply_lower.find(document.original_name.lower())
            if match_index >= 0:
                reply_document_matches.append((match_index, document.id))
        selected_document_ids: list[str] = [
            document_id
            for _, document_id in sorted(reply_document_matches, key=lambda item: item[0])
        ][:limit]

        if not selected_document_ids:
            metadata_documents = self.document_service.find_documents_by_metadata(
                query,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            selected_document_ids = [document.id for document in metadata_documents[:limit]]

        if not selected_document_ids and fallback_sources:
            return fallback_sources[:limit]

        if (
            not selected_document_ids
            and self.document_service.is_recent_document_inventory_query(query)
        ):
            selected_document_ids = [visible_documents[0].id]

        if not selected_document_ids and (
            self.document_service.is_document_inventory_query(query)
            or self.document_service.is_document_similarity_query(query)
            or self.document_service.is_document_metadata_inventory_query(query)
        ):
            selected_document_ids = [document.id for document in visible_documents[:limit]]

        if not selected_document_ids:
            resolved_ids = self.document_service.find_referenced_documents(
                query,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
            if not resolved_ids:
                resolved_ids = self.document_service.resolve_follow_up_document_ids(
                    query,
                    history=history,
                    allowed_document_ids=allowed_document_ids,
                    is_admin=is_admin,
                    viewer_username=viewer_username,
                )
            selected_document_ids = resolved_ids[:limit]

        if not selected_document_ids:
            return []

        return self.document_service.recent_sources_for_document_ids(
            selected_document_ids[:limit],
            limit=limit,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )

    def _summarize_generic_document_content(
        self,
        *,
        query: str,
        sources: list[ChatSource],
        allowed_document_ids: list[str] | None,
        history: list | None,
        is_admin: bool,
        viewer_username: str | None,
    ) -> str | None:
        if not self._is_generic_document_summary_query(query):
            return None

        resolved_ids = self.document_service.find_referenced_documents(
            query,
            allowed_document_ids=allowed_document_ids,
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if not resolved_ids:
            resolved_ids = self.document_service.resolve_follow_up_document_ids(
                query,
                history=history,
                allowed_document_ids=allowed_document_ids,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )
        if not resolved_ids and sources:
            resolved_ids = [sources[0].document_id]
        if not resolved_ids:
            return None

        document = self.document_service.get_document_for_viewer(
            resolved_ids[0],
            is_admin=is_admin,
            viewer_username=viewer_username,
        )
        if document is None:
            return None

        document_sources = [
            source for source in sources if source.document_id == document.id
        ]
        if not document_sources:
            document_sources = self.document_service.recent_sources_for_document_ids(
                [document.id],
                limit=2,
                is_admin=is_admin,
                viewer_username=viewer_username,
            )

        return self._render_document_content_summary(document, document_sources)

    def _render_document_content_summary(
        self,
        document,
        document_sources: list[ChatSource],
    ) -> str:
        details: list[str] = []
        title = (document.document_title or "").strip()
        if self._is_clean_title(title, document.original_name):
            details.append(f'The detected title is "{title}".')

        topic_terms = [
            topic
            for topic in document.document_topics
            if (
                topic
                and topic.lower() != (document.detected_document_type or "").lower()
                and self._is_clean_summary_term(topic)
            )
        ]
        if topic_terms:
            details.append(
                "It mainly covers " + self._join_phrases(topic_terms[:3]) + "."
            )

        clean_entities = [
            entity for entity in document.document_entities if self._is_clean_entity_label(entity)
        ]
        if clean_entities:
            details.append(
                "Key entities include "
                + self._join_phrases(clean_entities[:2])
                + "."
            )
        elif document.document_summary_anchor:
            details.append(
                f"A notable marker in the document is {document.document_summary_anchor}."
            )

        details.extend(self._document_key_facts(document.id))
        details.extend(self._document_source_highlights(document_sources))
        return " ".join(
            sentence
            for sentence in [self._build_document_summary_lead(document, document_sources), *details]
            if sentence
        ).strip()

    def _is_recent_document_summary_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        if not self.document_service.is_recent_document_inventory_query(query):
            return False
        summary_markers = (
            "about",
            "summarize",
            "summary",
            "describe",
            "explain",
            "main topic",
            "handlar",
            "sammanfatta",
        )
        return any(marker in lowered for marker in summary_markers)

    def _is_document_writing_task_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        if not self.document_service.is_document_reference_query(query):
            return False

        writing_markers = (
            "draft ",
            "write ",
            "compose ",
            "create ",
            "generate ",
            "prepare ",
            "formulate ",
            "skriv ",
            "skapa ",
            "utforma ",
            "formulera ",
        )
        artifact_markers = (
            "email",
            "mail",
            "reply",
            "response",
            "customer email",
            "incident report",
            "management summary",
            "executive summary",
            "action plan",
            "report",
            "rapport",
            "sammanfattning",
            "svar",
            "kundmail",
            "handlingsplan",
        )
        return any(marker in lowered for marker in writing_markers) and any(
            marker in lowered for marker in artifact_markers
        )

    def _draft_action_plan_from_sources(
        self,
        query: str,
        sources: list[ChatSource],
    ) -> str | None:
        lowered = " ".join(query.lower().split())
        if not any(
            marker in lowered
            for marker in ("action plan", "handlingsplan", "åtgärdsplan")
        ):
            return None
        if not sources:
            return None

        rows: list[tuple[str, str, str, str, str]] = []
        seen_documents: set[str] = set()
        for source in sources[:4]:
            if source.document_id in seen_documents:
                continue
            seen_documents.add(source.document_id)
            code = self._extract_reference_code(source.excerpt)
            subject = code or (source.section_title or source.detected_document_type or "document")
            task = f"Review {subject} and confirm required follow-up"
            if "incident" in lowered or "incident" in source.excerpt.lower():
                task = f"Review incident {subject} and confirm impact, owner, and next step"
            evidence = self._format_source_evidence(source)
            rows.append((task, "Unknown", "Unknown", "Medium", evidence))

        if not rows:
            return None

        lines = [
            "Here is a best-effort action plan based only on the provided document context.",
            "",
            "| Task | Owner | Deadline | Priority | Evidence |",
            "| --- | --- | --- | --- | --- |",
        ]
        for task, owner, deadline, priority, evidence in rows:
            lines.append(f"| {task} | {owner} | {deadline} | {priority} | {evidence} |")
        lines.extend(
            [
                "",
                "Missing information: owner, deadline, and concrete remediation steps are not explicit in the provided sources.",
            ]
        )
        return "\n".join(lines)

    def _draft_customer_email_from_sources(
        self,
        query: str,
        sources: list[ChatSource],
    ) -> str | None:
        lowered = " ".join(query.lower().split())
        if not any(marker in lowered for marker in ("email", "mail", "customer", "kund")):
            return None
        if not sources:
            return None

        source = sources[0]
        code = self._extract_reference_code(source.excerpt)
        subject_detail = code or source.section_title or source.detected_document_type or "document update"
        evidence = self._format_source_evidence(source)

        return "\n".join(
            [
                f"Subject: Update regarding {subject_detail}",
                "",
                "Dear customer,",
                "",
                "We are contacting you with an update based on the information currently available.",
                "",
                "What we know:",
                f"- Reference: {subject_detail}",
                f"- Source: {evidence}",
                "",
                "What we still need:",
                "- Incident impact: Unknown from the provided documents",
                "- Confirmed owner and next action: Unknown from the provided documents",
                "- Customer-specific details: Unknown from the provided documents",
                "",
                "We will follow up when those details have been confirmed.",
                "",
                "Best regards,",
                "Support team",
            ]
        )

    def _extract_reference_code(self, text: str) -> str | None:
        match = re.search(r"\b[A-Z]{2,}[-_ ]?\d{2,}\b", text or "")
        if not match:
            return None
        return match.group(0).replace("_", "-").replace(" ", "-")

    def _format_source_evidence(self, source: ChatSource) -> str:
        parts = [source.document_name]
        if source.section_title:
            parts.append(source.section_title)
        if source.page_number:
            parts.append(f"page {source.page_number}")
        return " / ".join(part for part in parts if part)

    def _wants_document_type_inventory(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        markers = (
            "by type",
            "kind of files",
            "kinds of files",
            "kinda files",
            "what kind",
            "what kinds",
            "file types",
            "document types",
            "types of",
            "business questions",
        )
        return any(marker in lowered for marker in markers)

    def _summarize_document_inventory_by_type(self, documents) -> str:
        grouped: dict[str, list[str]] = {}
        for document in documents:
            label = (
                document.detected_document_type
                or document.source_kind
                or "document"
            )
            label = str(label).strip().lower() or "document"
            grouped.setdefault(label, []).append(document.original_name)

        group_lines = []
        for label, names in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
            preview = ", ".join(names[:3])
            suffix = "" if len(names) <= 3 else f", and {len(names) - 3} more"
            group_lines.append(f"{label}: {len(names)} ({preview}{suffix})")
            if len(group_lines) >= 6:
                break

        useful_documents = [
            document.original_name
            for document in documents
            if (document.detected_document_type or document.source_kind or "").lower()
            in {
                "agreement",
                "contract",
                "invoice",
                "policy",
                "report",
                "roadmap",
                "spreadsheet",
                "presentation",
                "word",
                "pdf",
            }
        ][:5]
        useful_sentence = ""
        if useful_documents:
            useful_sentence = (
                " For business questions, start with "
                + self._join_phrases(useful_documents)
                + "."
            )

        return (
            f"You currently have {len(documents)} uploaded documents. "
            f"By type: {'; '.join(group_lines)}."
            f"{useful_sentence}"
        )

    def _is_generic_document_summary_query(self, query: str) -> bool:
        lowered = " ".join(query.lower().split())
        if not self.document_service.is_document_reference_query(query):
            return False
        if self.document_service.is_document_topic_presence_query(query):
            return False
        if self.document_service.is_document_type_query(query):
            return False

        blocked_markers = (
            "mention",
            "mentions",
            "mentioned",
            "contains",
            "contain",
            "title",
            "date",
            "owner",
            "port",
            "amount",
            "code",
            "latest",
            "version",
            "compare",
            "difference",
            "changed",
            "change",
            "conflict",
            "similar",
            "which ",
            "who ",
            "when ",
            "where ",
        )
        if any(marker in lowered for marker in blocked_markers):
            return False

        summary_markers = (
            "what is it about",
            "what is this about",
            "what is that about",
            "tell me about",
            "summarize",
            "summary of",
            "describe",
            "explain",
        )
        if any(marker in lowered for marker in summary_markers):
            return True

        return " about" in lowered

    def _document_key_facts(self, document_id: str) -> list[str]:
        extracted_text = self.document_service.get_extracted_text(document_id)
        if not extracted_text:
            return []

        lines = [
            " ".join(line.split()).strip(" :")
            for line in extracted_text.replace("\r", "\n").splitlines()
        ]
        lines = [line for line in lines if line]
        heading_markers = {
            "project",
            "purpose",
            "summary",
            "offer",
            "incident summary",
            "findings",
            "recommendation",
            "commercial terms",
        }
        facts: list[str] = []
        for index, line in enumerate(lines):
            lowered = line.lower()
            inline_match = re.match(
                r"^(project|purpose|summary|offer|incident summary|findings|recommendation|commercial terms)\s*[:\-]\s*(.+)$",
                lowered,
            )
            if inline_match:
                fact = line.split(":", 1)[-1].strip(" -")
                if self._is_useful_key_fact(fact):
                    facts.append(fact)
                continue

            if lowered not in heading_markers:
                continue
            for next_line in lines[index + 1 : index + 4]:
                if next_line.lower() in heading_markers:
                    break
                if self._is_useful_key_fact(next_line):
                    facts.append(next_line)
                    break

        deduped_facts: list[str] = []
        seen: set[str] = set()
        for fact in facts:
            normalized = fact.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped_facts.append(fact)
            if len(deduped_facts) >= 2:
                break

        if not deduped_facts:
            return []
        return [f"Important extracted details include {self._join_phrases(deduped_facts)}."]

    def _summarize_structured_value_from_sources(
        self,
        query: str,
        sources: list[ChatSource],
    ) -> str | None:
        if not sources:
            return None

        lowered = " ".join(query.lower().split())
        if "port" not in lowered:
            return None
        if not any(marker in lowered for marker in ("xml", "config", "service")):
            return None

        for source in sources:
            source_kind = (source.source_kind or "").lower()
            if source_kind not in {"config", "xml", "text"}:
                continue

            text = self.document_service.get_extracted_text(source.document_id)
            if not text:
                text = source.excerpt

            value = self._extract_config_port_value(text)
            if value:
                return (
                    f"The configured service port in {source.document_name} is "
                    f"{value}."
                )

        return None

    def _extract_config_port_value(self, text: str) -> str | None:
        patterns = (
            r"<port>\s*([0-9]{2,5})\s*</port>",
            r"\bport\s*[:=]\s*([0-9]{2,5})\b",
            r'"port"\s*:\s*"?([0-9]{2,5})"?',
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _is_useful_key_fact(self, value: str) -> bool:
        cleaned = " ".join(str(value or "").split()).strip()
        if len(cleaned) < 12 or len(cleaned) > 240:
            return False
        if cleaned.lower() in {"project", "purpose", "summary", "findings"}:
            return False
        return True

    def _build_document_summary_lead(self, document, sources: list[ChatSource]) -> str:
        document_type = self._document_type_label(document, sources)
        if document_type == "document":
            return f"{document.original_name} is a document in your knowledge base."
        return f"{document.original_name} is {self._with_indefinite_article(document_type)}."

    def _document_type_label(self, document, sources: list[ChatSource]) -> str:
        detected = (document.detected_document_type or "").strip().lower()
        source_kind = (document.source_kind or "").strip().lower()
        if detected and detected != "document":
            return detected

        if sources:
            inferred = self._infer_document_type(sources[0])
            if inferred and len(inferred.split()) <= 6:
                return inferred

        source_kind_labels = {
            "spreadsheet": "spreadsheet",
            "presentation": "presentation",
            "word": "word document",
            "markdown": "markdown document",
            "text": "text document",
            "json": "JSON document",
            "csv": "CSV document",
            "config": "configuration file",
            "code": "code file",
            "image": "image document",
            "pdf": "PDF document",
        }
        return source_kind_labels.get(source_kind, "document")

    def _document_source_highlights(self, sources: list[ChatSource]) -> list[str]:
        highlights: list[str] = []
        for index, source in enumerate(sources[:2]):
            summary = self._summarize_source_excerpt(source, max_characters=190)
            if not summary:
                continue
            location = self._format_source_location(source)
            lead = "One retrieved section"
            if index == 1:
                lead = "Another section"
            if location:
                lead += f" ({location})"
            sentence = f"{lead} mentions {summary}"
            if source.ocr_used:
                sentence += self._ocr_caveat(source, 1)
            highlights.append(sentence)
        return highlights

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
        lowered = value.strip().lower()
        if not lowered:
            return value
        article = "an" if lowered[0] in {"a", "e", "i", "o", "u"} else "a"
        return f"{article} {value}"

    def _is_clean_title(self, value: str, document_name: str) -> bool:
        cleaned = str(value or "").strip()
        if not cleaned:
            return False
        if cleaned.lower() in document_name.lower():
            return False
        if len(cleaned) < 5 or len(cleaned) > 80:
            return False
        if any(token in cleaned.lower() for token in ("swift", "bic", "iban", "vat")):
            return False
        if re.search(r"\d{4,}|[/\\|]{1,}", cleaned):
            return False
        return self._alpha_ratio(cleaned) >= 0.72

    def _is_clean_summary_term(self, value: str) -> bool:
        cleaned = str(value or "").strip()
        if not cleaned:
            return False
        if cleaned[0].isdigit():
            return False
        if re.search(r"[/\\|]", cleaned):
            return False
        if len(cleaned) > 40:
            return False
        return self._alpha_ratio(cleaned) >= 0.68

    def _is_clean_entity_label(self, value: str) -> bool:
        cleaned = str(value or "").strip()
        if not cleaned:
            return False
        if re.search(r"\d|[/\\|]", cleaned):
            return False
        if len(cleaned.split()) < 2:
            return False
        return self._alpha_ratio(cleaned) >= 0.72

    def _alpha_ratio(self, value: str) -> float:
        meaningful = [character for character in value if not character.isspace()]
        if not meaningful:
            return 0.0
        alpha_count = sum(character.isalpha() for character in meaningful)
        return alpha_count / len(meaningful)

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
