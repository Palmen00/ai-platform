import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.config import settings
from app.schemas.connector import ConnectorBrowseRequest
from app.schemas.connector import ConnectorCreateRequest
from app.schemas.connector import ConnectorManifest
from app.schemas.connector import ConnectorUpdateRequest
from app.services.security import REDACTED_SECRET_VALUE, SecretStorageService, is_sensitive_provider_setting
from app.services.users import UserService


class ConnectorRegistryService:
    def __init__(self) -> None:
        self.connectors_dir = settings.connectors_dir
        self.secret_storage = SecretStorageService(settings.app_secrets_key)
        self.user_service = UserService()

    def list_connectors(self, *, redact_secrets: bool = True) -> list[ConnectorManifest]:
        connectors: list[ConnectorManifest] = []
        for path in sorted(self.connectors_dir.glob("*.json")):
            connectors.append(self._read_connector(path, redact_secrets=redact_secrets))

        return sorted(connectors, key=lambda item: item.updated_at, reverse=True)

    def get_connector(
        self,
        connector_id: str,
        *,
        redact_secrets: bool = False,
    ) -> ConnectorManifest | None:
        path = self._connector_path(connector_id)
        if not path.exists():
            return None

        return self._read_connector(path, redact_secrets=redact_secrets)

    def create_connector(self, payload: ConnectorCreateRequest) -> ConnectorManifest:
        now = datetime.now(UTC).isoformat()
        connector = ConnectorManifest(
            id=uuid4().hex,
            name=payload.name,
            provider=payload.provider,
            enabled=payload.enabled,
            auth_mode=payload.auth_mode,
            root_path=payload.root_path,
            container=payload.container,
            document_visibility=self._normalize_document_visibility(
                payload.document_visibility
            ),
            access_usernames=self._normalize_access_usernames(
                payload.access_usernames,
                visibility=payload.document_visibility,
            ),
            include_patterns=payload.include_patterns,
            exclude_patterns=payload.exclude_patterns,
            export_formats=payload.export_formats,
            provider_settings=payload.provider_settings,
            notes=payload.notes,
            created_at=now,
            updated_at=now,
        )
        self._write_connector(connector)
        return connector

    def create_preview_connector(
        self,
        payload: ConnectorBrowseRequest,
        *,
        now: str | None = None,
    ) -> ConnectorManifest:
        timestamp = now or datetime.now(UTC).isoformat()
        return ConnectorManifest(
            id="preview",
            name=f"{payload.provider} preview",
            provider=payload.provider,
            enabled=True,
            auth_mode=payload.auth_mode,
            root_path=payload.root_path,
            document_visibility=self._normalize_document_visibility("standard"),
            provider_settings=payload.provider_settings,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def update_connector(
        self,
        connector_id: str,
        payload: ConnectorUpdateRequest,
    ) -> ConnectorManifest | None:
        connector = self.get_connector(connector_id, redact_secrets=False)
        if connector is None:
            return None

        for field_name in (
            "name",
            "enabled",
            "auth_mode",
            "root_path",
            "container",
            "document_visibility",
            "access_usernames",
            "include_patterns",
            "exclude_patterns",
            "export_formats",
            "provider_settings",
            "notes",
            "last_sync_at",
        ):
            value = getattr(payload, field_name)
            if value is not None:
                if field_name == "provider_settings":
                    connector.provider_settings = self._merge_provider_settings(
                        current=connector.provider_settings,
                        incoming=value,
                    )
                elif field_name == "document_visibility":
                    connector.document_visibility = self._normalize_document_visibility(
                        value
                    )
                    connector.access_usernames = self._normalize_access_usernames(
                        connector.access_usernames,
                        visibility=connector.document_visibility,
                    )
                elif field_name == "access_usernames":
                    connector.access_usernames = self._normalize_access_usernames(
                        value,
                        visibility=connector.document_visibility,
                    )
                else:
                    setattr(connector, field_name, value)

        connector.updated_at = datetime.now(UTC).isoformat()
        self._write_connector(connector)
        return connector

    def delete_connector(self, connector_id: str) -> bool:
        path = self._connector_path(connector_id)
        if not path.exists():
            return False

        path.unlink()
        return True

    def _connector_path(self, connector_id: str) -> Path:
        return self.connectors_dir / f"{connector_id}.json"

    def to_public_manifest(self, connector: ConnectorManifest) -> ConnectorManifest:
        return connector.model_copy(
            update={
                "provider_settings": self.secret_storage.redact_provider_settings(
                    connector.provider_settings
                )
            }
        )

    def _merge_provider_settings(
        self,
        *,
        current: dict[str, str],
        incoming: dict[str, str],
    ) -> dict[str, str]:
        merged = {**current}
        for key, value in incoming.items():
            if value == REDACTED_SECRET_VALUE and is_sensitive_provider_setting(key):
                continue
            merged[key] = value
        return merged

    def _read_connector(
        self,
        path: Path,
        *,
        redact_secrets: bool,
    ) -> ConnectorManifest:
        with path.open("r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)

        provider_settings = payload.get("provider_settings")
        if isinstance(provider_settings, dict):
            payload["provider_settings"] = self.secret_storage.decrypt_provider_settings(
                {str(key): str(value) for key, value in provider_settings.items()}
            )

        connector = ConnectorManifest.model_validate(payload)
        return self.to_public_manifest(connector) if redact_secrets else connector

    def _write_connector(self, connector: ConnectorManifest) -> None:
        path = self._connector_path(connector.id)
        payload = connector.model_dump()
        payload["provider_settings"] = self.secret_storage.encrypt_provider_settings(
            connector.provider_settings
        )
        with path.open("w", encoding="utf-8") as file_handle:
            json.dump(payload, file_handle, ensure_ascii=True, indent=2)

    def _normalize_document_visibility(self, visibility: str | None) -> str:
        normalized = (visibility or "standard").strip().lower()
        if normalized not in {"standard", "hidden", "restricted"}:
            raise ValueError(
                "Connector document visibility must be 'standard', 'hidden', or 'restricted'."
            )
        return normalized

    def _normalize_access_usernames(
        self,
        access_usernames: list[str] | None,
        *,
        visibility: str,
    ) -> list[str]:
        if visibility != "restricted":
            return []

        normalized_requested: list[str] = []
        seen: set[str] = set()
        for username in access_usernames or []:
            normalized = username.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            normalized_requested.append(normalized)

        if not normalized_requested:
            raise ValueError(
                "Restricted connectors must allow at least one enabled user."
            )

        allowed_lookup = {
            user.username.strip().lower(): user.username
            for user in self.user_service.list_users()
            if user.enabled and user.username.strip()
        }
        resolved = [
            allowed_lookup[username]
            for username in normalized_requested
            if username in allowed_lookup
        ]
        if not resolved:
            raise ValueError(
                "Restricted connectors must allow at least one enabled user."
            )
        if len(resolved) != len(normalized_requested):
            raise ValueError(
                "One or more connector access usernames were not found or are disabled."
            )
        return resolved
