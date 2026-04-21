from __future__ import annotations

from datetime import UTC, datetime
import threading


class ActivityService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_user_activity_at = datetime.now(UTC)
        self._active_jobs: dict[str, int] = {}

    def touch_user_activity(self, source: str | None = None) -> None:
        del source
        with self._lock:
            self._last_user_activity_at = datetime.now(UTC)

    def begin_job(self, job_type: str) -> None:
        with self._lock:
            self._active_jobs[job_type] = self._active_jobs.get(job_type, 0) + 1

    def end_job(self, job_type: str) -> None:
        with self._lock:
            current = self._active_jobs.get(job_type, 0)
            if current <= 1:
                self._active_jobs.pop(job_type, None)
            else:
                self._active_jobs[job_type] = current - 1

    def seconds_since_user_activity(self) -> float:
        with self._lock:
            last_activity_at = self._last_user_activity_at
        return max((datetime.now(UTC) - last_activity_at).total_seconds(), 0.0)

    def has_active_jobs(self) -> bool:
        with self._lock:
            return any(count > 0 for count in self._active_jobs.values())

    def is_idle(self, idle_seconds: int) -> bool:
        if self.has_active_jobs():
            return False
        return self.seconds_since_user_activity() >= max(idle_seconds, 0)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            active_jobs = dict(self._active_jobs)
            last_user_activity_at = self._last_user_activity_at
        return {
            "last_user_activity_at": last_user_activity_at.isoformat(),
            "seconds_since_user_activity": max(
                (datetime.now(UTC) - last_user_activity_at).total_seconds(),
                0.0,
            ),
            "active_jobs": active_jobs,
        }


activity_service = ActivityService()
