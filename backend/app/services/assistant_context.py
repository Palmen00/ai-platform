from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings
from app.schemas.chat import ChatHistoryMessage, ChatSource


@dataclass(frozen=True)
class AssistantPack:
    name: str
    content: str


class AssistantContextService:
    def __init__(self) -> None:
        self.prompt_packs_dir = (
            settings.backend_root / "app" / "prompt_packs"
        )

    def build_runtime_context(self) -> str | None:
        if not settings.assistant_intelligence_enabled:
            return None

        timezone = self._resolve_timezone()
        now = datetime.now(timezone)
        iso_week = now.isocalendar().week

        return "\n".join(
            [
                f"Timezone: {settings.app_timezone}",
                f"Current local date: {now.strftime('%Y-%m-%d')}",
                f"Current local time: {now.strftime('%H:%M')}",
                f"Current weekday: {now.strftime('%A')}",
                f"Current ISO week: {iso_week}",
                "Use this runtime context for questions about today, current time, weekdays, or this week.",
            ]
        )

    def answer_runtime_question(self, user_message: str) -> str | None:
        if not settings.assistant_intelligence_enabled:
            return None

        normalized = " ".join(user_message.lower().split())
        if not self._looks_like_runtime_question(normalized):
            return None

        timezone = self._resolve_timezone()
        now = datetime.now(timezone)
        iso_week = now.isocalendar().week

        is_swedish = self._looks_swedish(normalized)
        weekday_name = self._weekday_name(now, swedish=is_swedish)
        date_text = now.strftime("%Y-%m-%d")
        time_text = now.strftime("%H:%M")

        asks_time = any(
            marker in normalized
            for marker in ("what time", "current time", "klockan", "hur mycket ar klockan", "vad ar klockan")
        )
        asks_week = any(
            marker in normalized
            for marker in ("week", "vecka", "iso week")
        )
        asks_day = any(
            marker in normalized
            for marker in ("today", "idag", "weekday", "vilken dag", "what day", "datum", "date")
        )

        if is_swedish:
            parts: list[str] = []
            if asks_day or not (asks_day or asks_week or asks_time):
                parts.append(f"Idag är det {weekday_name} {date_text}.")
            if asks_week:
                parts.append(f"Det är vecka {iso_week}.")
            if asks_time:
                parts.append(f"Lokal tid är {time_text} i tidszonen {settings.app_timezone}.")
            return " ".join(parts)

        parts = []
        if asks_day or not (asks_day or asks_week or asks_time):
            parts.append(f"Today is {weekday_name}, {date_text}.")
        if asks_week:
            parts.append(f"It is ISO week {iso_week}.")
        if asks_time:
            parts.append(f"Local time is {time_text} in timezone {settings.app_timezone}.")
        return " ".join(parts)

    def select_packs(
        self,
        user_message: str,
        history: list[ChatHistoryMessage],
        sources: list[ChatSource],
    ) -> list[AssistantPack]:
        if not settings.assistant_intelligence_enabled:
            return []

        pack_names = list(settings.assistant_base_packs)
        optional_pack_names = set(settings.assistant_optional_packs)
        combined_text = " ".join(
            [user_message, *[message.content for message in history[-4:]]]
        )

        if self._looks_like_code_question(combined_text) and "code" in optional_pack_names:
            pack_names.append("code")
        elif not sources and "reference" in optional_pack_names:
            pack_names.append("reference")

        unique_pack_names: list[str] = []
        for name in pack_names:
            if name not in unique_pack_names:
                unique_pack_names.append(name)

        return [
            pack for pack in (self._load_pack(name) for name in unique_pack_names) if pack
        ]

    def _resolve_timezone(self) -> ZoneInfo:
        try:
            return ZoneInfo(settings.app_timezone)
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    @lru_cache(maxsize=8)
    def _load_pack(self, name: str) -> AssistantPack | None:
        path = self.prompt_packs_dir / f"{name}.md"
        if not path.exists():
            return None

        content = path.read_text(encoding="utf-8").strip()
        if not content:
            return None

        return AssistantPack(name=name, content=content)

    def _looks_like_code_question(self, text: str) -> bool:
        normalized = text.lower()
        keywords = (
            "code",
            "python",
            "typescript",
            "javascript",
            "react",
            "next.js",
            "nextjs",
            "api",
            "backend",
            "frontend",
            "bug",
            "error",
            "stack trace",
            "docker",
            "sql",
            "regex",
            "script",
            "compile",
            "build",
            "debug",
            "function",
            "class",
            "install",
            "deploy",
            "ssh",
            "git",
            "terminal",
            "command",
        )
        return any(keyword in normalized for keyword in keywords) or bool(
            re.search(r"`[^`]+`", text)
        )

    def _looks_like_runtime_question(self, normalized: str) -> bool:
        document_markers = (
            "document",
            "documents",
            "file",
            "files",
            "uploaded",
            "upload",
            "pdf",
            "docx",
            "xlsx",
            "pptx",
            "json",
            "csv",
            "xml",
            "png",
            "jpg",
            "jpeg",
            "invoice",
            "report",
            "policy",
            "contract",
            "notes",
            "guide",
            "roadmap",
        )
        if any(marker in normalized for marker in document_markers):
            return False

        markers = (
            "today",
            "current time",
            "what time",
            "weekday",
            "what day",
            "date today",
            "what date",
            "iso week",
            "week is it",
            "idag",
            "vad ar det for dag",
            "vad är det för dag",
            "vilken dag",
            "vilken vecka",
            "vad ar det for vecka",
            "vad är det för vecka",
            "vad ar klockan",
            "vad är klockan",
            "datum",
            "vecka",
            "klockan",
        )
        return any(marker in normalized for marker in markers)

    def _looks_swedish(self, normalized: str) -> bool:
        swedish_markers = (
            "vad",
            "idag",
            "vecka",
            "klockan",
            "vilken",
            "dag",
            "är",
            "det",
        )
        return any(marker in normalized for marker in swedish_markers)

    def _weekday_name(self, now: datetime, *, swedish: bool) -> str:
        if not swedish:
            return now.strftime("%A")

        weekday_lookup = {
            0: "måndag",
            1: "tisdag",
            2: "onsdag",
            3: "torsdag",
            4: "fredag",
            5: "lördag",
            6: "söndag",
        }
        return weekday_lookup[now.weekday()]
