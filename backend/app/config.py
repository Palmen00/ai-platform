import base64
import json
import os
from pathlib import Path

from dotenv import load_dotenv


def _parse_cors_origins(raw_value: str) -> list[str]:
    return [origin.strip() for origin in raw_value.split(",") if origin.strip()]


def _parse_csv_values(raw_value: str) -> list[str]:
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def _decode_base64_env(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    return base64.b64decode(value, validate=True).decode("utf-8")


def _resolve_project_paths() -> tuple[Path, Path]:
    config_path = Path(__file__).resolve()
    candidates = [config_path.parents[2], config_path.parents[1]]

    for candidate in candidates:
        if (candidate / "backend" / "app").exists():
            return candidate, candidate / "backend"
        if (candidate / "app").exists() and (candidate / "requirements.txt").exists():
            return candidate, candidate

    fallback = config_path.parents[2]
    return fallback, fallback / "backend"


class Settings:
    def __init__(self) -> None:
        repo_root, backend_root = _resolve_project_paths()
        load_dotenv(repo_root / ".env", override=True)
        self._mutable_keys = (
            "ollama_base_url",
            "ollama_default_model",
            "ollama_embed_model",
            "qdrant_url",
            "retrieval_limit",
            "retrieval_min_score",
            "document_chunk_size",
            "document_chunk_overlap",
        )
        self.repo_root = repo_root
        self.backend_root = backend_root
        self.data_root = Path(os.getenv("DATA_ROOT", self.repo_root / "data"))
        self.app_data_root = Path(
            os.getenv("APP_DATA_ROOT", self.data_root / "app")
        )
        self.app_cache_dir = Path(
            os.getenv("APP_CACHE_DIR", self.app_data_root / "cache")
        )
        self.uploads_dir = Path(
            os.getenv("UPLOADS_DIR", self.data_root / "uploads")
        )
        self.qdrant_storage_dir = Path(
            os.getenv("QDRANT_STORAGE_DIR", self.data_root / "qdrant")
        )
        self.documents_metadata_dir = Path(
            os.getenv("DOCUMENTS_METADATA_DIR", self.app_data_root / "documents")
        )
        self.conversations_dir = Path(
            os.getenv("CONVERSATIONS_DIR", self.app_data_root / "conversations")
        )
        self.document_chunks_dir = Path(
            os.getenv("DOCUMENT_CHUNKS_DIR", self.documents_metadata_dir / "chunks")
        )
        self.document_extracted_text_dir = Path(
            os.getenv(
                "DOCUMENT_EXTRACTED_TEXT_DIR",
                self.documents_metadata_dir / "extracted",
            )
        )
        self.users_path = Path(
            os.getenv("USERS_PATH", self.app_data_root / "users.json")
        )
        self.connectors_dir = Path(
            os.getenv("CONNECTORS_DIR", self.app_data_root / "connectors")
        )
        self.local_connector_allowed_roots = [
            Path(path).expanduser().resolve()
            for path in _parse_csv_values(
                os.getenv("LOCAL_CONNECTOR_ALLOWED_ROOTS", "")
            )
        ]
        self.logs_dir = Path(os.getenv("LOGS_DIR", self.app_data_root / "logs"))
        self.ocr_data_dir = Path(
            os.getenv("OCR_DATA_DIR", self.app_data_root / "ocr" / "tessdata")
        )
        self.app_log_path = Path(
            os.getenv("APP_LOG_PATH", self.logs_dir / "application.log")
        )
        self.app_events_log_path = Path(
            os.getenv("APP_EVENTS_LOG_PATH", self.logs_dir / "events.jsonl")
        )
        self.document_chunk_size = int(os.getenv("DOCUMENT_CHUNK_SIZE", "1000"))
        self.document_chunk_overlap = int(
            os.getenv("DOCUMENT_CHUNK_OVERLAP", "150")
        )
        self.document_list_limit_default = max(
            1,
            int(os.getenv("DOCUMENT_LIST_LIMIT_DEFAULT", "200")),
        )
        self.document_upload_max_size_mb = max(
            1,
            int(os.getenv("DOCUMENT_UPLOAD_MAX_SIZE_MB", "75")),
        )
        self.document_upload_max_size_bytes = (
            self.document_upload_max_size_mb * 1024 * 1024
        )
        self.ocr_enabled = os.getenv("OCR_ENABLED", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.ocr_language = os.getenv("OCR_LANGUAGE", "eng+swe")
        self.ocr_min_characters = int(os.getenv("OCR_MIN_CHARACTERS", "80"))
        self.ocr_render_scale = float(os.getenv("OCR_RENDER_SCALE", "2.5"))
        self.ocr_psm_modes = [
            int(value.strip())
            for value in os.getenv("OCR_PSM_MODES", "3,6,11").split(",")
            if value.strip().isdigit()
        ] or [3, 6, 11]
        self.ocrmypdf_enabled = os.getenv("OCRMYPDF_ENABLED", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.ocrmypdf_use_docker = os.getenv("OCRMYPDF_USE_DOCKER", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.ocrmypdf_docker_image = os.getenv(
            "OCRMYPDF_DOCKER_IMAGE",
            "local-ai-ocrmypdf:latest",
        ).strip()
        self.ocrmypdf_timeout_seconds = int(
            os.getenv("OCRMYPDF_TIMEOUT_SECONDS", "180")
        )
        self.ocrmypdf_auto_build = os.getenv("OCRMYPDF_AUTO_BUILD", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.ocrmypdf_skip_big = int(os.getenv("OCRMYPDF_SKIP_BIG", "50"))
        self.ocrmypdf_cache_dir = Path(
            os.getenv("OCRMYPDF_CACHE_DIR", self.app_cache_dir / "ocrmypdf")
        )
        self.gliner_enabled = os.getenv("GLINER_ENABLED", "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.gliner_model_id = os.getenv(
            "GLINER_MODEL_ID",
            "urchade/gliner_small-v2.1",
        ).strip()
        self.gliner_threshold = float(os.getenv("GLINER_THRESHOLD", "0.4"))
        self.gliner_max_characters = int(os.getenv("GLINER_MAX_CHARACTERS", "12000"))
        self.gliner_window_size = int(os.getenv("GLINER_WINDOW_SIZE", "3200"))
        self.gliner_window_overlap = int(os.getenv("GLINER_WINDOW_OVERLAP", "300"))
        self.gliner_max_windows = int(os.getenv("GLINER_MAX_WINDOWS", "4"))
        self.gliner_backfill_existing = os.getenv("GLINER_BACKFILL_EXISTING", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.unstructured_enabled = os.getenv("UNSTRUCTURED_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.unstructured_max_elements = int(os.getenv("UNSTRUCTURED_MAX_ELEMENTS", "800"))
        self.tesseract_cmd = os.getenv("TESSERACT_CMD", "").strip()
        self.app_name = os.getenv("APP_NAME", "Local AI OS")
        self.app_env = os.getenv("APP_ENV", "dev")
        self.app_timezone = os.getenv("APP_TIMEZONE", "Europe/Stockholm").strip() or "Europe/Stockholm"
        self.assistant_intelligence_enabled = os.getenv(
            "ASSISTANT_INTELLIGENCE_ENABLED",
            "true",
        ).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.assistant_base_packs = _parse_csv_values(
            os.getenv("ASSISTANT_BASE_PACKS", "base,local-ai-os")
        )
        self.assistant_optional_packs = _parse_csv_values(
            os.getenv("ASSISTANT_OPTIONAL_PACKS", "code,reference")
        )
        self.starter_knowledge_enabled = os.getenv(
            "STARTER_KNOWLEDGE_ENABLED",
            "true",
        ).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.auth_enabled = os.getenv("AUTH_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.admin_username = os.getenv("ADMIN_USERNAME", "Admin").strip() or "Admin"
        self.admin_password_hash = _decode_base64_env(
            os.getenv("ADMIN_PASSWORD_HASH_B64", "")
        ) or os.getenv("ADMIN_PASSWORD_HASH", "").strip()
        self.admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
        self.admin_session_secret = os.getenv("ADMIN_SESSION_SECRET", "").strip()
        self.admin_session_ttl_hours = max(
            1,
            int(os.getenv("ADMIN_SESSION_TTL_HOURS", "12")),
        )
        self.admin_remember_me_ttl_days = max(
            1,
            int(os.getenv("ADMIN_REMEMBER_ME_TTL_DAYS", "30")),
        )
        self.admin_login_max_attempts = max(
            1,
            int(os.getenv("ADMIN_LOGIN_MAX_ATTEMPTS", "5")),
        )
        self.admin_login_lockout_minutes = max(
            1,
            int(os.getenv("ADMIN_LOGIN_LOCKOUT_MINUTES", "15")),
        )
        self.admin_login_ip_max_attempts = max(
            1,
            int(os.getenv("ADMIN_LOGIN_IP_MAX_ATTEMPTS", "20")),
        )
        self.admin_login_ip_window_seconds = max(
            30,
            int(os.getenv("ADMIN_LOGIN_IP_WINDOW_SECONDS", "300")),
        )
        self.admin_login_global_max_attempts = max(
            1,
            int(os.getenv("ADMIN_LOGIN_GLOBAL_MAX_ATTEMPTS", "200")),
        )
        self.admin_login_global_window_seconds = max(
            30,
            int(os.getenv("ADMIN_LOGIN_GLOBAL_WINDOW_SECONDS", "300")),
        )
        self.admin_session_cookie_name = os.getenv(
            "ADMIN_SESSION_COOKIE_NAME",
            "local_ai_admin_session",
        ).strip() or "local_ai_admin_session"
        self.admin_session_cookie_secure = os.getenv(
            "ADMIN_SESSION_COOKIE_SECURE",
            "false",
        ).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.admin_session_cookie_samesite = os.getenv(
            "ADMIN_SESSION_COOKIE_SAMESITE",
            "lax",
        ).strip().lower() or "lax"
        self.app_secrets_key = os.getenv("APP_SECRETS_KEY", "").strip()
        self.safe_mode_enabled = os.getenv("SAFE_MODE", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.low_impact_mode = os.getenv("LOW_IMPACT_MODE", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.idle_maintenance_enabled = os.getenv(
            "IDLE_MAINTENANCE_ENABLED",
            "true",
        ).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.idle_maintenance_poll_seconds = max(
            15,
            int(os.getenv("IDLE_MAINTENANCE_POLL_SECONDS", "45")),
        )
        self.idle_maintenance_user_idle_seconds = max(
            60,
            int(os.getenv("IDLE_MAINTENANCE_USER_IDLE_SECONDS", "240")),
        )
        self.idle_maintenance_batch_size = max(
            1,
            int(os.getenv("IDLE_MAINTENANCE_BATCH_SIZE", "1")),
        )
        self.ollama_embed_batch_size = max(
            1,
            int(os.getenv("OLLAMA_EMBED_BATCH_SIZE", "8")),
        )
        self.runtime_settings_path = Path(
            os.getenv("RUNTIME_SETTINGS_PATH", self.app_data_root / "settings.json")
        )
        self.qdrant_url = os.getenv("QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")
        self.qdrant_collection_name = os.getenv(
            "QDRANT_COLLECTION_NAME", "document_chunks"
        )
        self.ollama_base_url = os.getenv(
            "OLLAMA_BASE_URL", "http://127.0.0.1:11434"
        ).rstrip("/")
        self.sharepoint_tenant_id = os.getenv("SHAREPOINT_TENANT_ID", "").strip()
        self.sharepoint_client_id = os.getenv("SHAREPOINT_CLIENT_ID", "").strip()
        self.sharepoint_client_secret = os.getenv("SHAREPOINT_CLIENT_SECRET", "").strip()
        self.sharepoint_graph_base_url = os.getenv(
            "SHAREPOINT_GRAPH_BASE_URL",
            "https://graph.microsoft.com/v1.0",
        ).rstrip("/")
        self.google_drive_client_id = os.getenv("GOOGLE_DRIVE_CLIENT_ID", "").strip()
        self.google_drive_client_secret = os.getenv(
            "GOOGLE_DRIVE_CLIENT_SECRET",
            "",
        ).strip()
        self.google_drive_refresh_token = os.getenv(
            "GOOGLE_DRIVE_REFRESH_TOKEN",
            "",
        ).strip()
        self.google_drive_api_base_url = os.getenv(
            "GOOGLE_DRIVE_API_BASE_URL",
            "https://www.googleapis.com/drive/v3",
        ).rstrip("/")
        self.google_drive_token_url = os.getenv(
            "GOOGLE_DRIVE_TOKEN_URL",
            "https://oauth2.googleapis.com/token",
        ).strip()
        self.ollama_default_model = os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.2:3b")
        self.ollama_embed_model = os.getenv(
            "OLLAMA_EMBED_MODEL", "nomic-embed-text"
        )
        self.retrieval_limit = int(os.getenv("RETRIEVAL_LIMIT", "4"))
        self.retrieval_min_score = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.45"))
        self.cors_origins = _parse_cors_origins(
            os.getenv(
                "BACKEND_CORS_ORIGINS",
                "http://localhost:3000,http://127.0.0.1:3000",
            )
        )
        self._ensure_directories()
        self._apply_runtime_overrides()

    def _ensure_directories(self) -> None:
        directories = (
            self.data_root,
            self.app_data_root,
            self.app_cache_dir,
            self.conversations_dir,
            self.uploads_dir,
            self.documents_metadata_dir,
            self.document_chunks_dir,
            self.document_extracted_text_dir,
            self.connectors_dir,
            self.logs_dir,
            self.ocr_data_dir,
            self.ocrmypdf_cache_dir,
            self.qdrant_storage_dir,
        )

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def _load_runtime_overrides(self) -> dict[str, object]:
        if not self.runtime_settings_path.exists():
            return {}

        with self.runtime_settings_path.open("r", encoding="utf-8") as file_handle:
            payload = json.load(file_handle)

        return payload if isinstance(payload, dict) else {}

    def _apply_runtime_overrides(self) -> None:
        overrides = self._load_runtime_overrides()
        for key in self._mutable_keys:
            if key not in overrides:
                continue

            value = overrides[key]
            if key in {
                "retrieval_limit",
                "document_chunk_size",
                "document_chunk_overlap",
            }:
                setattr(self, key, int(value))
            elif key == "retrieval_min_score":
                setattr(self, key, float(value))
            elif isinstance(value, str):
                normalized = value.rstrip("/") if key in {"ollama_base_url", "qdrant_url"} else value
                setattr(self, key, normalized)

    def get_runtime_settings_payload(self) -> dict[str, object]:
        return {
            "ollama_base_url": self.ollama_base_url,
            "ollama_default_model": self.ollama_default_model,
            "ollama_embed_model": self.ollama_embed_model,
            "qdrant_url": self.qdrant_url,
            "retrieval_limit": self.retrieval_limit,
            "retrieval_min_score": self.retrieval_min_score,
            "document_chunk_size": self.document_chunk_size,
            "document_chunk_overlap": self.document_chunk_overlap,
        }

    def update_runtime_settings(self, payload: dict[str, object]) -> dict[str, object]:
        current = self.get_runtime_settings_payload()
        next_settings = {**current, **payload}

        self.runtime_settings_path.parent.mkdir(parents=True, exist_ok=True)
        with self.runtime_settings_path.open("w", encoding="utf-8") as file_handle:
            json.dump(next_settings, file_handle, ensure_ascii=True, indent=2)

        self._apply_runtime_overrides()
        return self.get_runtime_settings_payload()


settings = Settings()
