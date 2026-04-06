import json
import logging
from collections import deque
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler

from app.config import settings
from app.schemas.logs import LogEvent

LOGGER_NAME = "local_ai_os"


def setup_logging() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        settings.app_log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger() -> logging.Logger:
    return setup_logging()


def log_event(
    event_type: str,
    message: str,
    status: str = "info",
    **details: object,
) -> None:
    event = LogEvent(
        timestamp=datetime.now(UTC).isoformat(),
        event_type=event_type,
        status=status,
        message=message,
        details=details,
    )

    with settings.app_events_log_path.open("a", encoding="utf-8") as file_handle:
        file_handle.write(json.dumps(event.model_dump(), ensure_ascii=True) + "\n")

    logger = get_logger()
    log_message = f"{event_type}: {message}"
    if details:
        log_message = f"{log_message} | {json.dumps(details, ensure_ascii=True)}"

    if status == "error":
        logger.error(log_message)
    elif status == "warning":
        logger.warning(log_message)
    else:
        logger.info(log_message)


def read_recent_log_lines(limit: int = 200) -> list[str]:
    if not settings.app_log_path.exists():
        return []

    with settings.app_log_path.open("r", encoding="utf-8", errors="ignore") as file_handle:
        return list(deque((line.rstrip() for line in file_handle), maxlen=limit))


def read_recent_events(limit: int = 100) -> list[LogEvent]:
    if not settings.app_events_log_path.exists():
        return []

    with settings.app_events_log_path.open(
        "r", encoding="utf-8", errors="ignore"
    ) as file_handle:
        lines = list(deque(file_handle, maxlen=limit))

    events: list[LogEvent] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
            events.append(LogEvent.model_validate(payload))
        except Exception:
            continue

    return events
