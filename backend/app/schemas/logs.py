from pydantic import BaseModel, Field


class LogEvent(BaseModel):
    timestamp: str
    event_type: str
    status: str = "info"
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class LogsResponse(BaseModel):
    events: list[LogEvent]
    raw_lines: list[str]
