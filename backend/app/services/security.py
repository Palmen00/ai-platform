from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

PASSWORD_HASH_PREFIX = "scrypt"
PASSWORD_HASH_N = 2**14
PASSWORD_HASH_R = 8
PASSWORD_HASH_P = 1
PASSWORD_HASH_DKLEN = 32
CONNECTOR_SECRET_PREFIX = "enc::"
REDACTED_SECRET_VALUE = "[stored securely]"
SENSITIVE_PROVIDER_SETTING_TOKENS = (
    "secret",
    "token",
    "password",
    "api_key",
    "apikey",
    "private_key",
    "client_secret",
    "clientsecret",
    "refresh_token",
    "refreshtoken",
    "access_key",
    "accesskey",
)


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _urlsafe_b64decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("utf-8"))


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password cannot be empty.")

    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_HASH_N,
        r=PASSWORD_HASH_R,
        p=PASSWORD_HASH_P,
        dklen=PASSWORD_HASH_DKLEN,
    )
    return (
        f"{PASSWORD_HASH_PREFIX}${PASSWORD_HASH_N}${PASSWORD_HASH_R}"
        f"${PASSWORD_HASH_P}${_urlsafe_b64encode(salt)}"
        f"${_urlsafe_b64encode(derived)}"
    )


def verify_password_hash(password: str, password_hash: str) -> bool:
    if not password or not password_hash:
        return False

    try:
        algorithm, n, r, p, encoded_salt, encoded_hash = password_hash.split("$", 5)
    except ValueError:
        return False

    if algorithm != PASSWORD_HASH_PREFIX:
        return False

    try:
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_urlsafe_b64decode(encoded_salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=PASSWORD_HASH_DKLEN,
        )
    except (TypeError, ValueError):
        return False

    return hmac.compare_digest(_urlsafe_b64encode(derived), encoded_hash)


def generate_app_secrets_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("utf-8")


def is_sensitive_provider_setting(key: str) -> bool:
    normalized = key.strip().lower()
    return any(token in normalized for token in SENSITIVE_PROVIDER_SETTING_TOKENS)


class SecretStorageService:
    def __init__(self, key: str) -> None:
        self._key = key.strip()

    @property
    def configured(self) -> bool:
        return bool(self._key)

    def encrypt_provider_settings(
        self,
        provider_settings: dict[str, str],
    ) -> dict[str, str]:
        encrypted: dict[str, str] = {}
        for key, value in provider_settings.items():
            normalized_value = value.strip()
            if not is_sensitive_provider_setting(key) or not normalized_value:
                encrypted[key] = value
                continue

            if normalized_value.startswith(CONNECTOR_SECRET_PREFIX):
                encrypted[key] = normalized_value
                continue

            encrypted[key] = f"{CONNECTOR_SECRET_PREFIX}{self.encrypt_text(normalized_value)}"

        return encrypted

    def decrypt_provider_settings(
        self,
        provider_settings: dict[str, str],
    ) -> dict[str, str]:
        decrypted: dict[str, str] = {}
        for key, value in provider_settings.items():
            normalized_value = value.strip()
            if normalized_value.startswith(CONNECTOR_SECRET_PREFIX):
                decrypted[key] = self.decrypt_text(
                    normalized_value[len(CONNECTOR_SECRET_PREFIX) :]
                )
                continue

            decrypted[key] = value

        return decrypted

    def redact_provider_settings(
        self,
        provider_settings: dict[str, str],
    ) -> dict[str, str]:
        redacted: dict[str, str] = {}
        for key, value in provider_settings.items():
            if is_sensitive_provider_setting(key) and value.strip():
                redacted[key] = REDACTED_SECRET_VALUE
            else:
                redacted[key] = value
        return redacted

    def encrypt_text(self, value: str) -> str:
        fernet = self._build_fernet()
        return fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt_text(self, value: str) -> str:
        fernet = self._build_fernet()
        return fernet.decrypt(value.encode("utf-8")).decode("utf-8")

    def _build_fernet(self):
        if not self.configured:
            raise ValueError(
                "APP_SECRETS_KEY must be configured before storing encrypted secrets."
            )

        try:
            from cryptography.fernet import Fernet
        except ImportError as exc:
            raise RuntimeError(
                "The 'cryptography' package is required for encrypted secret storage. "
                "Install backend dependencies again."
            ) from exc

        return Fernet(self._key.encode("utf-8"))
