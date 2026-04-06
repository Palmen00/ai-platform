import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.config import settings
from app.schemas.connector import ConnectorBrowseRequest
from app.schemas.connector import ConnectorCreateRequest
from app.schemas.connector import ConnectorManifest
from app.schemas.connector import ConnectorUpdateRequest


class ConnectorRegistryService:
    def __init__(self) -> None:
        self.connectors_dir = settings.connectors_dir

    def list_connectors(self) -> list[ConnectorManifest]:
        connectors: list[ConnectorManifest] = []
        for path in sorted(self.connectors_dir.glob("*.json")):
            with path.open("r", encoding="utf-8") as file_handle:
                payload = json.load(file_handle)
                connectors.append(ConnectorManifest.model_validate(payload))

        return sorted(connectors, key=lambda item: item.updated_at, reverse=True)

    def get_connector(self, connector_id: str) -> ConnectorManifest | None:
        path = self._connector_path(connector_id)
        if not path.exists():
            return None

        with path.open("r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)

        return ConnectorManifest.model_validate(payload)

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
            provider_settings=payload.provider_settings,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def update_connector(
        self,
        connector_id: str,
        payload: ConnectorUpdateRequest,
    ) -> ConnectorManifest | None:
        connector = self.get_connector(connector_id)
        if connector is None:
            return None

        for field_name in (
            "name",
            "enabled",
            "auth_mode",
            "root_path",
            "container",
            "include_patterns",
            "exclude_patterns",
            "export_formats",
            "provider_settings",
            "notes",
            "last_sync_at",
        ):
            value = getattr(payload, field_name)
            if value is not None:
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

    def _write_connector(self, connector: ConnectorManifest) -> None:
        path = self._connector_path(connector.id)
        with path.open("w", encoding="utf-8") as file_handle:
            json.dump(connector.model_dump(), file_handle, ensure_ascii=True, indent=2)
