from pydantic import BaseModel


class AuthStatusResponse(BaseModel):
    auth_enabled: bool
    auth_configured: bool
    authenticated: bool
    safe_mode_enabled: bool
    session_expires_at: str | None = None


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    token: str
    expires_at: str
    auth_enabled: bool
    auth_configured: bool
    authenticated: bool = True
    safe_mode_enabled: bool
