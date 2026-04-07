from collections import OrderedDict
from difflib import SequenceMatcher
import re

from app.schemas.chat import ChatHistoryMessage, ChatSource
from app.services.assistant_context import AssistantContextService
from app.services.ollama import OllamaService


class GenerationService:
    def __init__(self) -> None:
        self.assistant_context_service = AssistantContextService()
        self.ollama_service = OllamaService()

    @property
    def default_model(self) -> str:
        return self.ollama_service.default_model

    def generate_chat_reply(
        self,
        model: str,
        history: list[ChatHistoryMessage],
        user_message: str,
        sources: list[ChatSource],
    ) -> str:
        context_summary = self._build_context_summary(sources)
        runtime_context = self.assistant_context_service.build_runtime_context()
        assistant_packs = self.assistant_context_service.select_packs(
            user_message=user_message,
            history=history,
            sources=sources,
        )
        prompt = self.ollama_service.build_prompt(
            history=history,
            user_message=user_message,
            sources=sources,
            context_summary=context_summary,
            runtime_context=runtime_context,
            assistant_packs=assistant_packs,
        )
        return self.ollama_service.generate_reply(model=model, prompt=prompt)

    def generate_grounded_document_reply(
        self,
        model: str,
        history: list[ChatHistoryMessage],
        user_message: str,
        sources: list[ChatSource],
    ) -> str:
        context_summary = self._build_context_summary(sources)
        runtime_context = self.assistant_context_service.build_runtime_context()
        assistant_packs = self.assistant_context_service.select_packs(
            user_message=user_message,
            history=history,
            sources=sources,
        )
        prompt = self.ollama_service.build_grounded_document_prompt(
            history=history,
            user_message=user_message,
            sources=sources,
            context_summary=context_summary,
            runtime_context=runtime_context,
            assistant_packs=assistant_packs,
        )
        return self.ollama_service.generate_reply(model=model, prompt=prompt)

    def _build_context_summary(self, sources: list[ChatSource]) -> str | None:
        if not sources:
            return None

        grouped_sources: OrderedDict[str, dict[str, object]] = OrderedDict()

        for source in sorted(sources, key=lambda item: item.score, reverse=True):
            group = grouped_sources.setdefault(
                source.document_id,
                {
                    "name": source.document_name,
                    "top_score": source.score,
                    "locations": [],
                    "snippets": [],
                },
            )
            group["top_score"] = max(float(group["top_score"]), source.score)

            location = self._format_source_location(source)
            if location and location not in group["locations"]:
                group["locations"].append(location)

            snippet = self._clean_excerpt(source.excerpt)
            if snippet and not self._contains_similar_snippet(
                group["snippets"],
                snippet,
            ):
                group["snippets"].append(snippet)

        ordered_groups = sorted(
            grouped_sources.values(),
            key=lambda item: float(item["top_score"]),
            reverse=True,
        )
        if not ordered_groups:
            return None

        lines: list[str] = []
        ocr_source_count = sum(1 for source in sources if source.ocr_used)
        if len(ordered_groups) == 1:
            lines.append(
                f"Primary supporting document: {ordered_groups[0]['name']}."
            )
        else:
            lines.append(
                "Relevant evidence appears across "
                f"{len(ordered_groups)} documents. Start with the strongest match, "
                "then merge overlapping points into one coherent explanation."
            )

        if ocr_source_count:
            lines.append(
                "Some supporting passages come from OCR. Paraphrase carefully, prefer the likely meaning over noisy wording, and mention uncertainty only when the text is genuinely unclear."
            )

        for group in ordered_groups[:3]:
            locations = ", ".join(list(group["locations"])[:2])
            snippets = list(group["snippets"])[:2]
            line = f"- {group['name']}"
            if locations:
                line += f" ({locations})"
            if snippets:
                line += f": {snippets[0]}"
                if len(snippets) > 1:
                    line += f" Also: {snippets[1]}"
            lines.append(line)

        return "\n".join(lines)

    def _format_source_location(self, source: ChatSource) -> str:
        parts: list[str] = []
        if source.section_title:
            parts.append(source.section_title)
        if source.page_number is not None:
            parts.append(f"page {source.page_number}")
        return " / ".join(parts)

    def _clean_excerpt(self, excerpt: str, max_characters: int = 180) -> str:
        cleaned = excerpt.replace("...", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-|")
        cleaned = re.sub(r"^(Section:\s*[^|]+?\|\s*)", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^(Page\s+\d+\s*\|\s*)", "", cleaned, flags=re.IGNORECASE)
        cleaned = self._polish_ocr_excerpt(cleaned)

        if len(cleaned) <= max_characters:
            return cleaned

        trimmed = cleaned[:max_characters]
        if " " in trimmed:
            trimmed = trimmed.rsplit(" ", 1)[0]
        return trimmed.strip(" ,;:-") + "..."

    def _contains_similar_snippet(
        self, snippets: list[object], candidate: str
    ) -> bool:
        normalized_candidate = candidate.lower()
        for snippet in snippets:
            normalized_existing = str(snippet).lower()
            if SequenceMatcher(
                None,
                normalized_existing,
                normalized_candidate,
            ).ratio() >= 0.8:
                return True
        return False

    def _polish_ocr_excerpt(self, excerpt: str) -> str:
        cleaned = excerpt
        replacements = (
            (r"\bDecease insurance\b", "death insurance"),
            (r"\bExpenses concerning doctor and medicine\b", "expenses for doctor and medicine"),
            (r"\boc0idenys\b", "accident"),
            (r"\bsiclknes\$\b", "sickness"),
            (r"\bLor Mospilalttion\b", "Hospitalization"),
        )
        for pattern, replacement in replacements:
            cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-|")
        return cleaned
