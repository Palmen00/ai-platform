import shutil
from pathlib import Path

from app.config import settings
from app.schemas.settings import CleanupTargetResult


def _path_size(path: Path) -> int:
    if not path.exists():
        return 0

    if path.is_file():
        return path.stat().st_size

    return sum(child.stat().st_size for child in path.rglob("*") if child.is_file())


class MaintenanceService:
    def __init__(self) -> None:
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
