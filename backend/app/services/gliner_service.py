from __future__ import annotations

from collections.abc import Iterable
import re

from app.config import settings

try:
    from gliner import GLiNER
except Exception:  # pragma: no cover - optional dependency
    GLiNER = None


class GLiNEREntityService:
    _model: GLiNER | None = None
    _load_error: str | None = None
    _prediction_cache: dict[tuple[str, str | None], list[tuple[str, str, float]]] = {}

    BASE_LABELS = [
        "company",
        "organization",
        "person",
        "project",
        "product",
        "date",
        "location",
        "invoice number",
        "contract name",
        "policy name",
    ]
    ENTITY_LABELS = {
        "company",
        "organization",
        "project",
        "contract name",
        "policy name",
    }

    def enabled(self) -> bool:
        if settings.low_impact_mode:
            return False
        return settings.gliner_enabled

    def extract_candidate_entities(
        self,
        text: str,
        document_type: str | None = None,
    ) -> list[tuple[str, str, float]]:
        if not self.enabled():
            return []

        model = self._get_model()
        if model is None:
            return []

        labels = self._labels_for_document_type(document_type)
        windows = self._build_windows(text)
        if not windows:
            return []

        cache_key = (
            self._entity_key(text[: min(len(text), settings.gliner_max_characters)]),
            document_type or "",
        )
        cached = self.__class__._prediction_cache.get(cache_key)
        if cached is not None:
            return cached

        candidates: list[tuple[str, str, float]] = []
        seen: set[tuple[str, str]] = set()
        for window in windows:
            try:
                predictions = model.predict_entities(
                    window,
                    labels,
                    threshold=settings.gliner_threshold,
                )
            except Exception:
                continue

            for prediction in predictions:
                label = str(prediction.get("label", "")).strip().lower()
                entity_text = " ".join(str(prediction.get("text", "")).split()).strip()
                score = float(prediction.get("score", 0.0))
                if label not in self.ENTITY_LABELS or not entity_text:
                    continue

                normalized_key = self._entity_key(entity_text)
                if not normalized_key:
                    continue

                key = (label, normalized_key)
                if key in seen:
                    continue
                seen.add(key)
                candidates.append((entity_text, label, score))

        candidates.sort(key=lambda item: (item[2], len(item[0])), reverse=True)
        limited_candidates = candidates[:16]
        if len(self.__class__._prediction_cache) > 64:
            oldest_key = next(iter(self.__class__._prediction_cache))
            self.__class__._prediction_cache.pop(oldest_key, None)
        self.__class__._prediction_cache[cache_key] = limited_candidates
        return limited_candidates

    def _get_model(self) -> GLiNER | None:
        if GLiNER is None:
            self._load_error = "gliner-not-installed"
            return None

        if self.__class__._model is not None:
            return self.__class__._model

        if self.__class__._load_error:
            return None

        try:
            self.__class__._model = GLiNER.from_pretrained(settings.gliner_model_id)
        except Exception as exc:  # pragma: no cover - model download/load failure
            self.__class__._load_error = str(exc)
            return None

        return self.__class__._model

    def _labels_for_document_type(self, document_type: str | None) -> list[str]:
        labels = list(self.BASE_LABELS)
        if document_type == "invoice":
            return labels
        if document_type == "contract":
            return labels
        if document_type == "policy":
            return labels
        return labels

    def _build_windows(self, text: str) -> list[str]:
        normalized = " ".join(text.split())
        if not normalized:
            return []

        capped = normalized[: settings.gliner_max_characters]
        if len(capped) <= settings.gliner_window_size:
            return [capped]

        windows: list[str] = []
        start = 0
        while start < len(capped) and len(windows) < settings.gliner_max_windows:
            end = min(start + settings.gliner_window_size, len(capped))
            window = capped[start:end].strip()
            if window:
                windows.append(window)
            if end >= len(capped):
                break
            start = max(end - settings.gliner_window_overlap, start + 1)

        return windows

    def _entity_key(self, value: str) -> str:
        normalized = value.lower()
        normalized = normalized.replace("&", " and ")
        normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized
