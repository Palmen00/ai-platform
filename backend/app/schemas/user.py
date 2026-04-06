from typing import Literal

from pydantic import BaseModel, Field


UserRole = Literal["admin", "viewer"]


class LocalUserRecord(BaseModel):
    id: str
    username: str
    role: UserRole = "viewer"
    enabled: bool = True
    password_hash: str
    created_at: str
    updated_at: str
    last_login_at: str | None = None


class UserWorkspaceStats(BaseModel):
    conversation_count: int = 0
    message_count: int = 0
    conversation_storage_bytes: int = 0
    accessible_document_count: int = 0
    accessible_document_storage_bytes: int = 0


class LocalUserSummary(BaseModel):
    id: str
    username: str
    role: UserRole = "viewer"
    enabled: bool = True
    created_at: str
    updated_at: str
    last_login_at: str | None = None
    stats: UserWorkspaceStats = Field(default_factory=UserWorkspaceStats)


class UserListResponse(BaseModel):
    users: list[LocalUserSummary] = Field(default_factory=list)


class UserResponse(BaseModel):
    user: LocalUserSummary


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: UserRole = "viewer"
    enabled: bool = True


class UserUpdateRequest(BaseModel):
    username: str | None = None
    password: str | None = None
    role: UserRole | None = None
    enabled: bool | None = None
