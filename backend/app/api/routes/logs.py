from fastapi import APIRouter, Depends, Query

from app.schemas.logs import LogsResponse
from app.services.auth import require_admin_from_either_header
from app.services.logging_service import (
    read_recent_audit_events,
    read_recent_events,
    read_recent_log_lines,
)

router = APIRouter(
    prefix="/logs",
    tags=["logs"],
    dependencies=[Depends(require_admin_from_either_header)],
)


@router.get("", response_model=LogsResponse)
def get_logs(
    event_limit: int = Query(default=50, ge=1, le=200),
    line_limit: int = Query(default=120, ge=10, le=500),
    audit_only: bool = Query(default=False),
) -> LogsResponse:
    return LogsResponse(
        events=(
            read_recent_audit_events(limit=event_limit)
            if audit_only
            else read_recent_events(limit=event_limit)
        ),
        raw_lines=[] if audit_only else read_recent_log_lines(limit=line_limit),
    )
