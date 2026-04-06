from pydantic import BaseModel

from app.schemas.user import LocalUserSummary, UserRole


class AuthStatusResponse(BaseModel):
    auth_enabled: bool
    auth_configured: bool
    authenticated: bool
    safe_mode_enabled: bool
    username: str | None = None
    role: UserRole | None = None
    session_expires_at: str | None = None


class LoginRequest(BaseModel):
    username: str = "admin"
    password: str


class LoginResponse(BaseModel):
    expires_at: str
    auth_enabled: bool
    auth_configured: bool
    authenticated: bool = True
    safe_mode_enabled: bool
    username: str
    role: UserRole


class UserListEnvelope(BaseModel):
    users: list[LocalUserSummary]
