from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8765
    database: str = "agri_vision.sqlite3"
    media_dir: str = "media"
    api_key: str | None = None
    inference_url: str | None = None
    inference_api_key: str | None = None
    inference_model_version: str = "external-unconfigured"
    inference_timeout: float = 10.0

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            host=os.getenv("AGRI_VISION_HOST", cls.host),
            port=_positive_int("AGRI_VISION_PORT", cls.port),
            database=os.getenv("AGRI_VISION_DATABASE", cls.database),
            media_dir=os.getenv("AGRI_VISION_MEDIA_DIR", cls.media_dir),
            api_key=os.getenv("AGRI_VISION_API_KEY") or None,
            inference_url=os.getenv("AGRI_VISION_INFERENCE_URL") or None,
            inference_api_key=os.getenv("AGRI_VISION_INFERENCE_API_KEY") or None,
            inference_model_version=os.getenv("AGRI_VISION_INFERENCE_MODEL_VERSION", cls.inference_model_version),
            inference_timeout=_positive_float("AGRI_VISION_INFERENCE_TIMEOUT", cls.inference_timeout),
        )


def validate_runtime_security(host: str, api_key: str | None) -> None:
    """Prevent accidental unauthenticated exposure on a non-loopback bind."""
    if api_key:
        return
    if host.strip().lower() in {"localhost", "ip6-localhost"}:
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        raise ValueError("api_key_required_for_non_loopback_host") from None
    if address.is_loopback:
        return
    raise ValueError("api_key_required_for_non_loopback_host")


def _positive_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    parsed = int(value)
    if parsed < 1 or parsed > 65535:
        raise ValueError(f"{name}_out_of_range")
    return parsed


def _positive_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    parsed = float(value)
    if parsed <= 0 or parsed > 300:
        raise ValueError(f"{name}_out_of_range")
    return parsed
