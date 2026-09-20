from cryptography.fernet import Fernet, InvalidToken
import hashlib
import hmac

from orchestrator.config import get_settings


class SecretCodec:
    def __init__(self) -> None:
        settings = get_settings()
        key = settings.secret_encryption_key
        if settings.app_env == "production" and not key:
            raise RuntimeError("SECRET_ENCRYPTION_KEY is required in production")
        self._fernet = Fernet(key.encode()) if key else None

    def encrypt(self, value: str | None) -> str | None:
        if not value:
            return value
        if self._fernet:
            return "fernet:" + self._fernet.encrypt(value.encode()).decode()
        if get_settings().app_env == "production":
            raise RuntimeError("SECRET_ENCRYPTION_KEY is required in production")
        return "dev-plain:" + value

    def decrypt(self, value: str | None) -> str | None:
        if not value:
            return value
        if value.startswith("fernet:"):
            if not self._fernet:
                raise RuntimeError("Secret encryption key is unavailable")
            try:
                return self._fernet.decrypt(value.removeprefix("fernet:").encode()).decode()
            except InvalidToken as exc:
                raise RuntimeError("Could not decrypt provider secret") from exc
        if value.startswith("dev-plain:"):
            return value.removeprefix("dev-plain:")
        return value


secret_codec = SecretCodec()


def secret_fingerprint(value: str | None, namespace: str = "") -> str | None:
    if not value:
        return None
    key = (get_settings().secret_encryption_key or get_settings().app_name).encode()
    return hmac.new(key, f"{namespace}\0{value}".encode(), hashlib.sha256).hexdigest()
