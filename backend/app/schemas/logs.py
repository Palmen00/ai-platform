from pydantic import BaseModel, Field


class LogEvent(BaseModel):
    timestamp: str
    event_type: str
    category: str = "app"
    status: str = "info"
    message: str
    actor_user_id: str | None = None
    actor_username: str | None = None
    actor_role: str | None = None
    details: dict[str, object] = Field(default_factory=dict)


class LogsResponse(BaseModel):
    events: list[LogEvent]
    raw_lines: list[str]
