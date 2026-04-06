from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Cookie, Depends, Header, HTTPException, Response

from app.config import settings
from app.schemas.user import LocalUserRecord, UserRole
from app.services.security import verify_password_hash
from app.services.users import UserService


@dataclass
class UserSession:
    user_id: str
    username: str
    role: UserRole
    expires_at: datetime

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class AuthService:
    def __init__(self) -> None:
        self.user_service = UserService()

    @property
    def auth_enabled(self) -> bool:
        return settings.auth_enabled

    @property
    def auth_configured(self) -> bool:
        return bool(self.user_service.users_configured() and settings.admin_session_secret)

    @property
    def auth_active(self) -> bool:
        return self.auth_enabled and self.auth_configured

    @property
    def safe_mode_enabled(self) -> bool:
        return settings.safe_mode_enabled

    def authenticate_user(self, username: str, password: str) -> LocalUserRecord | None:
        user = self.user_service.get_user_by_username(username)
        if user is None or not user.enabled:
            return None

        if not verify_password_hash(password, user.password_hash):
            return None

        return user

    def has_authenticated_access(self, token: str | None) -> bool:
        if not self.auth_active:
            return True
        return self.validate_session_token(token) is not None

    def has_admin_access(self, token: str | None) -> bool:
        if not self.auth_active:
            return True
        session = self.validate_session_token(token)
        return session is not None and session.is_admin

    def issue_session_token(self, user: LocalUserRecord) -> tuple[str, datetime]:
        expires_at = datetime.now(UTC) + timedelta(hours=settings.admin_session_ttl_hours)
        payload = {
            "sub": user.id,
            "username": user.username,
            "role": user.role,
            "exp": int(expires_at.timestamp()),
        }
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        payload_token = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
        signature = hmac.new(
            settings.admin_session_secret.encode("utf-8"),
            payload_token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"{payload_token}.{signature}", expires_at

    def set_admin_session_cookie(
        self,
        response: Response,
        *,
        token: str,
        expires_at: datetime,
    ) -> None:
        response.set_cookie(
            key=settings.admin_session_cookie_name,
            value=token,
            httponly=True,
            secure=settings.admin_session_cookie_secure,
            samesite=settings.admin_session_cookie_samesite,
            expires=int(expires_at.timestamp()),
            max_age=settings.admin_session_ttl_hours * 60 * 60,
            path="/",
        )

    def clear_admin_session_cookie(self, response: Response) -> None:
        response.delete_cookie(
            key=settings.admin_session_cookie_name,
            httponly=True,
            secure=settings.admin_session_cookie_secure,
            samesite=settings.admin_session_cookie_samesite,
            path="/",
        )

    def validate_session_token(self, token: str | None) -> UserSession | None:
        if not self.auth_active:
            return None
        if not token:
            return None

        try:
            payload_token, signature = token.split(".", 1)
        except ValueError:
            return None

        expected_signature = hmac.new(
            settings.admin_session_secret.encode("utf-8"),
            payload_token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_signature):
            return None

        try:
            padded = payload_token + "=" * (-len(payload_token) % 4)
            payload = json.loads(
                base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
            )
        except Exception:
            return None

        try:
            expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
        except Exception:
            return None

        if expires_at <= datetime.now(UTC):
            return None

        user_id = str(payload.get("sub", "")).strip()
        username = str(payload.get("username", "")).strip()
        role = str(payload.get("role", "")).strip()
        if not user_id or not username or role not in {"admin", "viewer"}:
            return None

        user = self.user_service.get_user(user_id)
        if user is None or not user.enabled:
            return None

        if user.username != username or user.role != role:
            return None

        return UserSession(
            user_id=user.id,
            username=user.username,
            role=user.role,
            expires_at=expires_at,
        )


auth_service = AuthService()


def get_session_token(
    session_cookie: str | None = Cookie(
        default=None,
        alias=settings.admin_session_cookie_name,
    ),
    authorization: str | None = Header(default=None),
    x_admin_session: str | None = Header(default=None, alias="X-Admin-Session"),
) -> str | None:
    if session_cookie:
        return session_cookie

    if x_admin_session:
        return x_admin_session

    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return None


def get_current_session(token: str | None = Depends(get_session_token)) -> UserSession | None:
    return auth_service.validate_session_token(token)


def require_authenticated_session(
    session: UserSession | None = Depends(get_current_session),
) -> UserSession | None:
    if not auth_service.auth_active:
        return None
    if session is not None:
        return session
    raise HTTPException(status_code=401, detail="Authentication required.")


def require_admin_from_either_header(
    session: UserSession | None = Depends(get_current_session),
) -> UserSession | None:
    if not auth_service.auth_active:
        return None
    if session is not None and session.is_admin:
        return session
    raise HTTPException(status_code=401, detail="Admin authentication required.")


def ensure_safe_mode_allows(action_label: str) -> None:
    if not auth_service.safe_mode_enabled:
        return

    raise HTTPException(
        status_code=403,
        detail=f"Safe mode is enabled. {action_label} is currently blocked.",
    )


def get_actor_log_fields(session: UserSession | None) -> dict[str, str]:
    if session is None:
        return {}

    return {
        "actor_user_id": session.user_id,
        "actor_username": session.username,
        "actor_role": session.role,
    }
