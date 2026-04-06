from __future__ import annotations

from pathlib import Path

from app.config import settings

try:
    from unstructured.partition.auto import partition
except Exception:  # pragma: no cover - optional dependency
    partition = None


class UnstructuredPartitionService:
    def enabled(self) -> bool:
        return settings.unstructured_enabled and partition is not None

    def extract_document_title(
        self,
        file_path: Path,
        content_type: str,
    ) -> str | None:
        if not self.enabled():
            return None

        try:
            elements = partition(filename=str(file_path))
        except Exception:
            return None

        for element in elements[:24]:
            element_type = type(element).__name__
            element_text = " ".join(str(element).split()).strip()
            if element_type in {"Title", "Header"} and element_text:
                return element_text

        return None

    def extract_sections(
        self,
        file_path: Path,
        content_type: str,
        fallback_title: str,
    ) -> list[dict[str, str | int | None]]:
        if not self.enabled():
            return []

        suffix = file_path.suffix.lower()
        if suffix not in {".pdf", ".txt", ".md"} and content_type not in {
            "application/pdf",
            "text/plain",
            "text/markdown",
        }:
            return []

        try:
            elements = partition(filename=str(file_path))
        except Exception:
            return []

        sections: list[dict[str, str | int | None]] = []
        current_title = fallback_title or "Document"
        current_page: int | None = None
        buffer: list[str] = []
        document_title = self.extract_document_title(file_path, content_type) or current_title

        def flush() -> None:
            content = "\n".join(line for line in buffer if line.strip()).strip()
            if not content:
                return
            sections.append(
                {
                    "title": current_title,
                    "content": content,
                    "page_number": current_page,
                }
            )

        for element in elements[: settings.unstructured_max_elements]:
            element_text = " ".join(str(element).split()).strip()
            if not element_text:
                continue

            element_type = type(element).__name__
            metadata = getattr(element, "metadata", None)
            page_number = getattr(metadata, "page_number", None)

            if element_type in {"Title", "Header"}:
                if (
                    element_text == document_title
                    and not sections
                    and not buffer
                ):
                    current_title = document_title
                    current_page = int(page_number) if page_number else current_page
                    continue
                flush()
                buffer = []
                current_title = element_text
                current_page = int(page_number) if page_number else current_page
                continue

            if page_number:
                current_page = int(page_number)
            buffer.append(element_text)

        flush()
        return sections
