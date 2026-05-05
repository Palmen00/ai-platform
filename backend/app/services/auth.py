from __future__ import annotations

import base64
from collections import deque
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import Cookie, Depends, HTTPException, Response

from app.config import settings
from app.schemas.user import LocalUserRecord, UserRole
from app.services.security import verify_password_hash
from app.services.users import UserService


@dataclass
class UserSession:
    user_id: str
    username: str
    role: UserRole
    session_version: int
    expires_at: datetime

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


@dataclass
class AuthenticationResult:
    status: Literal["ok", "invalid", "locked"]
    user: LocalUserRecord | None = None
    locked_until: datetime | None = None
    remaining_attempts: int | None = None


class AuthService:
    def __init__(self) -> None:
        self.user_service = UserService()
        self._ip_login_attempts: dict[str, deque[datetime]] = {}
        self._global_login_attempts: deque[datetime] = deque()

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

    def authenticate_user(self, username: str, password: str) -> AuthenticationResult:
        user = self.user_service.get_user_by_username(username)
        if user is None or not user.enabled:
            return AuthenticationResult(status="invalid")

        if self.user_service.is_locked(user):
            return AuthenticationResult(
                status="locked",
                user=user,
                locked_until=datetime.fromisoformat(user.locked_until) if user.locked_until else None,
            )

        if not verify_password_hash(password, user.password_hash):
            updated_user = self.user_service.record_failed_login(user.id)
            if updated_user is not None and self.user_service.is_locked(updated_user):
                return AuthenticationResult(
                    status="locked",
                    user=updated_user,
                    locked_until=datetime.fromisoformat(updated_user.locked_until)
                    if updated_user.locked_until
                    else None,
                )
            return AuthenticationResult(
                status="invalid",
                user=updated_user or user,
                remaining_attempts=self.user_service.get_remaining_login_attempts(
                    updated_user or user
                ),
            )

        return AuthenticationResult(status="ok", user=user)

    def has_authenticated_access(self, token: str | None) -> bool:
        if not self.auth_active:
            return True
        return self.validate_session_token(token) is not None

    def has_admin_access(self, token: str | None) -> bool:
        if not self.auth_active:
            return True
        session = self.validate_session_token(token)
        return session is not None and session.is_admin

    def issue_session_token(
        self,
        user: LocalUserRecord,
        *,
        ttl: timedelta | None = None,
    ) -> tuple[str, datetime]:
        session_ttl = ttl or timedelta(hours=settings.admin_session_ttl_hours)
        expires_at = datetime.now(UTC) + session_ttl
        payload = {
            "sub": user.id,
            "username": user.username,
            "role": user.role,
            "ver": user.session_version,
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
        max_age_seconds: int,
    ) -> None:
        response.set_cookie(
            key=settings.admin_session_cookie_name,
            value=token,
            httponly=True,
            secure=settings.admin_session_cookie_secure,
            samesite=settings.admin_session_cookie_samesite,
            expires=int(expires_at.timestamp()),
            max_age=max_age_seconds,
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
        try:
            session_version = int(payload.get("ver", 1))
        except (TypeError, ValueError):
            return None

        if not user_id or not username or role not in {"admin", "viewer"}:
            return None

        user = self.user_service.get_user(user_id)
        if user is None or not user.enabled:
            return None

        if (
            user.username != username
            or user.role != role
            or user.session_version != session_version
        ):
            return None

        return UserSession(
            user_id=user.id,
            username=user.username,
            role=user.role,
            session_version=user.session_version,
            expires_at=expires_at,
        )

    def is_login_rate_limited(self, client_ip: str | None) -> bool:
        self._prune_login_attempts()
        if len(self._global_login_attempts) >= settings.admin_login_global_max_attempts:
            return True
        if not client_ip:
            return False
        ip_attempts = self._ip_login_attempts.get(client_ip)
        return bool(
            ip_attempts
            and len(ip_attempts) >= settings.admin_login_ip_max_attempts
        )

    def record_login_attempt(self, client_ip: str | None) -> None:
        now = datetime.now(UTC)
        self._global_login_attempts.append(now)
        if client_ip:
            self._ip_login_attempts.setdefault(client_ip, deque()).append(now)
        self._prune_login_attempts()

    def _prune_login_attempts(self) -> None:
        now = datetime.now(UTC)
        global_cutoff = now - timedelta(seconds=settings.admin_login_global_window_seconds)
        while self._global_login_attempts and self._global_login_attempts[0] < global_cutoff:
            self._global_login_attempts.popleft()

        ip_cutoff = now - timedelta(seconds=settings.admin_login_ip_window_seconds)
        for client_ip in list(self._ip_login_attempts.keys()):
            attempts = self._ip_login_attempts[client_ip]
            while attempts and attempts[0] < ip_cutoff:
                attempts.popleft()
            if not attempts:
                self._ip_login_attempts.pop(client_ip, None)


auth_service = AuthService()


def get_session_token(
    session_cookie: str | None = Cookie(
        default=None,
        alias=settings.admin_session_cookie_name,
    ),
) -> str | None:
    return session_cookie


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
