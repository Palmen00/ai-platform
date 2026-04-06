from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Header, HTTPException

from app.config import settings


@dataclass
class AdminSession:
    expires_at: datetime


class AuthService:
    @property
    def auth_enabled(self) -> bool:
        return settings.auth_enabled

    @property
    def auth_configured(self) -> bool:
        return bool(settings.admin_password and settings.admin_session_secret)

    @property
    def auth_active(self) -> bool:
        return self.auth_enabled and self.auth_configured

    @property
    def safe_mode_enabled(self) -> bool:
        return settings.safe_mode_enabled

    def is_admin_authenticated(self, token: str | None) -> bool:
        return self.validate_admin_token(token) is not None

    def has_admin_access(self, token: str | None) -> bool:
        if not self.auth_active:
            return True
        return self.is_admin_authenticated(token)

    def verify_password(self, password: str) -> bool:
        if not self.auth_configured:
            return False

        return hmac.compare_digest(password, settings.admin_password)

    def issue_admin_token(self) -> tuple[str, datetime]:
        expires_at = datetime.now(UTC) + timedelta(
            hours=settings.admin_session_ttl_hours
        )
        payload = {
            "role": "admin",
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

    def validate_admin_token(self, token: str | None) -> AdminSession | None:
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

        if payload.get("role") != "admin":
            return None

        try:
            expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
        except Exception:
            return None

        if expires_at <= datetime.now(UTC):
            return None

        return AdminSession(expires_at=expires_at)


auth_service = AuthService()


def get_admin_token(
    authorization: str | None = Header(default=None),
    x_admin_session: str | None = Header(default=None, alias="X-Admin-Session"),
) -> str | None:
    if x_admin_session:
        return x_admin_session

    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return None


def require_admin_from_either_header(
    x_admin_session: str | None = Header(default=None, alias="X-Admin-Session"),
    authorization: str | None = Header(default=None),
) -> None:
    token = x_admin_session
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    if auth_service.validate_admin_token(token) is not None:
        return

    if not auth_service.auth_active:
        return

    raise HTTPException(status_code=401, detail="Admin authentication required.")


def ensure_safe_mode_allows(action_label: str) -> None:
    if not auth_service.safe_mode_enabled:
        return

    raise HTTPException(
        status_code=403,
        detail=f"Safe mode is enabled. {action_label} is currently blocked.",
    )
