from __future__ import annotations

from datetime import UTC, datetime
import shutil
from pathlib import Path
import threading
import time

from app.config import settings
from app.schemas.document import DocumentMaintenanceStatus
from app.schemas.settings import CleanupTargetResult
from app.services.activity import activity_service
from app.services.documents import DocumentService
from app.services.logging_service import log_event


def _path_size(path: Path) -> int:
    if not path.exists():
        return 0

    if path.is_file():
        return path.stat().st_size

    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())


class MaintenanceService:
    def __init__(self) -> None:
        self.document_service = DocumentService()
        self._cleanable_targets = {
            "cache": {
                "label": "App cache",
                "path": settings.app_cache_dir,
            },
            "logs": {
                "label": "Logs",
                "path": settings.logs_dir,
            },
        }
        self._idle_worker_lock = threading.Lock()
        self._idle_worker_thread: threading.Thread | None = None
        self._idle_worker_stop = threading.Event()
        self._last_idle_run_at: str | None = None

    def start_idle_worker(self) -> None:
        if not settings.idle_maintenance_enabled:
            return

        with self._idle_worker_lock:
            if self._idle_worker_thread and self._idle_worker_thread.is_alive():
                return

            self._idle_worker_stop.clear()
            self._idle_worker_thread = threading.Thread(
                target=self._idle_worker_loop,
                daemon=True,
                name="idle-maintenance-worker",
            )
            self._idle_worker_thread.start()

    def stop_idle_worker(self) -> None:
        self._idle_worker_stop.set()
        with self._idle_worker_lock:
            worker = self._idle_worker_thread
            self._idle_worker_thread = None

        if worker and worker.is_alive():
            worker.join(timeout=3)

    def cleanup_targets(self, targets: list[str]) -> list[CleanupTargetResult]:
        normalized_targets: list[str] = []
        for target in targets:
            if target not in normalized_targets:
                normalized_targets.append(target)

        unsupported = [
            target for target in normalized_targets if target not in self._cleanable_targets
        ]
        if unsupported:
            raise ValueError(
                f"Unsupported cleanup targets: {', '.join(sorted(unsupported))}"
            )

        results: list[CleanupTargetResult] = []
        for target in normalized_targets:
            target_config = self._cleanable_targets[target]
            if target == "cache":
                removed_bytes = self._clear_directory_contents(target_config["path"])
            else:
                removed_bytes = self._clear_logs_directory(target_config["path"])

            results.append(
                CleanupTargetResult(
                    key=target,
                    label=str(target_config["label"]),
                    removed_bytes=removed_bytes,
                )
            )

        return results

    def run_idle_maintenance_step(self, *, force: bool = False) -> list[str]:
        if not force:
            if not settings.idle_maintenance_enabled:
                return []
            if not activity_service.is_idle(settings.idle_maintenance_user_idle_seconds):
                return []

        refreshed_documents = self.document_service.backfill_document_intelligence(
            limit=settings.idle_maintenance_batch_size,
        )
        if not refreshed_documents:
            return []

        self._last_idle_run_at = datetime.now(UTC).isoformat()
        refreshed_ids = [document.id for document in refreshed_documents]
        log_event(
            "maintenance.idle_enrichment",
            "Idle maintenance refreshed document intelligence.",
            category="audit",
            refreshed_count=len(refreshed_documents),
            refreshed_document_ids=refreshed_ids,
            refreshed_document_names=[document.original_name for document in refreshed_documents],
            forced=force,
        )
        return refreshed_ids

    def get_idle_status(self) -> DocumentMaintenanceStatus:
        activity_snapshot = activity_service.snapshot()
        pending_documents = self.document_service.count_background_intelligence_backlog()
        return DocumentMaintenanceStatus(
            enabled=settings.idle_maintenance_enabled,
            poll_seconds=settings.idle_maintenance_poll_seconds,
            user_idle_seconds=settings.idle_maintenance_user_idle_seconds,
            batch_size=settings.idle_maintenance_batch_size,
            last_run_at=self._last_idle_run_at,
            pending_documents=pending_documents,
            seconds_since_user_activity=float(
                activity_snapshot.get("seconds_since_user_activity", 0.0)
            ),
            active_jobs={
                str(key): int(value)
                for key, value in dict(activity_snapshot.get("active_jobs", {})).items()
            },
        )

    def _idle_worker_loop(self) -> None:
        poll_seconds = settings.idle_maintenance_poll_seconds

        while not self._idle_worker_stop.wait(poll_seconds):
            try:
                self.run_idle_maintenance_step()
            except Exception as exc:  # noqa: BLE001
                log_event(
                    "maintenance.idle_enrichment",
                    "Idle maintenance step failed.",
                    status="warning",
                    error=str(exc),
                )
            time.sleep(0.1)

    def _clear_directory_contents(self, path: Path) -> int:
        path.mkdir(parents=True, exist_ok=True)
        removed_bytes = 0

        for child in path.iterdir():
            removed_bytes += _path_size(child)
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)

        return removed_bytes

    def _clear_logs_directory(self, path: Path) -> int:
        path.mkdir(parents=True, exist_ok=True)
        removed_bytes = 0
        preserved_files = {
            settings.app_log_path.resolve(),
            settings.app_events_log_path.resolve(),
        }

        for child in path.iterdir():
            child_path = child.resolve()
            if child.is_file() and child_path in preserved_files:
                removed_bytes += child.stat().st_size
                child.write_text("", encoding="utf-8")
                continue

            removed_bytes += _path_size(child)
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)

        settings.app_log_path.parent.mkdir(parents=True, exist_ok=True)
        settings.app_log_path.touch(exist_ok=True)
        settings.app_events_log_path.touch(exist_ok=True)
        return removed_bytes


maintenance_service = MaintenanceService()
