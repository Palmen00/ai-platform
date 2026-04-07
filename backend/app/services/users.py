from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.config import settings
from app.schemas.user import LocalUserRecord, LocalUserSummary, UserCreateRequest, UserUpdateRequest
from app.services.security import hash_password


class UserService:
    def __init__(self) -> None:
        self.users_path = settings.users_path
        self.users_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_bootstrap_admin()

    def list_users(self) -> list[LocalUserRecord]:
        if not self.users_path.exists():
            return []

        with self.users_path.open("r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)

        if not isinstance(payload, list):
            return []

        users = [LocalUserRecord.model_validate(item) for item in payload]
        return sorted(users, key=lambda item: (item.role != "admin", item.username.lower()))

    def list_user_summaries(self) -> list[LocalUserSummary]:
        return [self.to_summary(user) for user in self.list_users()]

    def get_user(self, user_id: str) -> LocalUserRecord | None:
        return next((user for user in self.list_users() if user.id == user_id), None)

    def get_user_by_username(self, username: str) -> LocalUserRecord | None:
        normalized = username.strip().lower()
        return next(
            (user for user in self.list_users() if user.username.lower() == normalized),
            None,
        )

    def users_configured(self) -> bool:
        return any(user.enabled for user in self.list_users())

    def create_user(self, payload: UserCreateRequest) -> LocalUserRecord:
        username = self._normalize_username(payload.username)
        if self.get_user_by_username(username) is not None:
            raise ValueError("A user with that username already exists.")

        now = datetime.now(UTC).isoformat()
        user = LocalUserRecord(
            id=uuid4().hex,
            username=username,
            role=payload.role,
            enabled=payload.enabled,
            password_hash=hash_password(payload.password),
            created_at=now,
            updated_at=now,
        )
        users = self.list_users()
        users.append(user)
        self._write_users(users)
        return user

    def update_user(self, user_id: str, payload: UserUpdateRequest) -> LocalUserRecord | None:
        users = self.list_users()
        target = next((user for user in users if user.id == user_id), None)
        if target is None:
            return None

        if payload.username is not None:
            next_username = self._normalize_username(payload.username)
            existing = self.get_user_by_username(next_username)
            if existing is not None and existing.id != target.id:
                raise ValueError("A user with that username already exists.")
            target.username = next_username

        if payload.role is not None:
            target.role = payload.role

        if payload.enabled is not None:
            target.enabled = payload.enabled

        if payload.password is not None and payload.password.strip():
            target.password_hash = hash_password(payload.password.strip())
            target.session_version = max(1, target.session_version) + 1

        target.updated_at = datetime.now(UTC).isoformat()
        self._ensure_active_admin(users, changing_user_id=target.id)
        self._write_users(users)
        return target

    def record_login(self, user_id: str) -> None:
        users = self.list_users()
        target = next((user for user in users if user.id == user_id), None)
        if target is None:
            return

        now = datetime.now(UTC).isoformat()
        target.last_login_at = now
        target.updated_at = now
        target.failed_login_attempts = 0
        target.locked_until = None
        self._write_users(users)

    def is_locked(self, user: LocalUserRecord) -> bool:
        if not user.locked_until:
            return False

        try:
            locked_until = datetime.fromisoformat(user.locked_until)
        except ValueError:
            return False

        return locked_until > datetime.now(UTC)

    def get_remaining_login_attempts(self, user: LocalUserRecord) -> int:
        remaining = settings.admin_login_max_attempts - user.failed_login_attempts
        return max(0, remaining)

    def record_failed_login(self, user_id: str) -> LocalUserRecord | None:
        users = self.list_users()
        target = next((user for user in users if user.id == user_id), None)
        if target is None:
            return None

        target.failed_login_attempts = max(0, target.failed_login_attempts) + 1
        if target.failed_login_attempts >= settings.admin_login_max_attempts:
            locked_until = datetime.now(UTC) + timedelta(
                minutes=settings.admin_login_lockout_minutes
            )
            target.locked_until = locked_until.isoformat()
            target.failed_login_attempts = 0
        else:
            target.locked_until = None

        target.updated_at = datetime.now(UTC).isoformat()
        self._write_users(users)
        return target

    def clear_lockout(self, user_id: str) -> LocalUserRecord | None:
        users = self.list_users()
        target = next((user for user in users if user.id == user_id), None)
        if target is None:
            return None

        target.failed_login_attempts = 0
        target.locked_until = None
        target.updated_at = datetime.now(UTC).isoformat()
        self._write_users(users)
        return target

    def to_summary(self, user: LocalUserRecord) -> LocalUserSummary:
        return LocalUserSummary.model_validate(user.model_dump(exclude={"password_hash"}))

    def _ensure_bootstrap_admin(self) -> None:
        if self.list_users():
            return

        bootstrap_hash = settings.admin_password_hash
        if not bootstrap_hash and settings.admin_password:
            bootstrap_hash = hash_password(settings.admin_password)

        if not bootstrap_hash:
            return

        now = datetime.now(UTC).isoformat()
        bootstrap_admin = LocalUserRecord(
            id=uuid4().hex,
            username=self._normalize_username(settings.admin_username),
            role="admin",
            enabled=True,
            password_hash=bootstrap_hash,
            created_at=now,
            updated_at=now,
        )
        self._write_users([bootstrap_admin])

    def _ensure_active_admin(
        self,
        users: list[LocalUserRecord],
        *,
        changing_user_id: str | None = None,
    ) -> None:
        if not any(user.enabled and user.role == "admin" for user in users):
            if changing_user_id:
                raise ValueError("At least one enabled admin user is required.")
            raise ValueError("No enabled admin users remain.")

    def _normalize_username(self, username: str) -> str:
        normalized = username.strip()
        if not normalized:
            raise ValueError("Username cannot be empty.")
        return normalized

    def _write_users(self, users: list[LocalUserRecord]) -> None:
        self.users_path.parent.mkdir(parents=True, exist_ok=True)
        with self.users_path.open("w", encoding="utf-8") as file_handle:
            json.dump(
                [user.model_dump() for user in users],
                file_handle,
                ensure_ascii=True,
                indent=2,
            )
