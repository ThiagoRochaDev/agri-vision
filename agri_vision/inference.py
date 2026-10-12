from __future__ import annotations

from dataclasses import dataclass
import base64
import json
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class InferenceResult:
    prediction: float | None
    confidence: float
    model_version: str
    status: str


class InferenceEngine(Protocol):
    model_version: str

    def infer(self, media_path: Path | None, metadata: dict[str, Any], task: str) -> InferenceResult:
        """Return a prediction only when the engine is valid for the campaign task."""


class PendingInferenceEngine:
    model_version = "no-model-configured"

    def infer(self, media_path: Path | None, metadata: dict[str, Any], task: str) -> InferenceResult:
        return InferenceResult(None, 0.0, self.model_version, "pending_model")


class HttpInferenceEngine:
    def __init__(self, url: str, model_version: str, api_key: str | None = None, timeout: float = 10.0) -> None:
        if not url.strip():
            raise ValueError("inference_url_required")
        if not model_version.strip():
            raise ValueError("inference_model_version_required")
        if timeout <= 0:
            raise ValueError("inference_timeout_must_be_positive")
        self.url = url
        self.model_version = model_version
        self.api_key = api_key
        self.timeout = timeout

    def infer(self, media_path: Path | None, metadata: dict[str, Any], task: str) -> InferenceResult:
        if media_path is None or not media_path.exists():
            return InferenceResult(None, 0.0, self.model_version, "input_missing")
        try:
            payload = {
                "task": task,
                "model_version": self.model_version,
                "capture_metadata": metadata,
                "media_base64": base64.b64encode(media_path.read_bytes()).decode("ascii"),
            }
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            request = Request(self.url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urlopen(request, timeout=self.timeout) as response:
                if response.status < 200 or response.status >= 300:
                    return InferenceResult(None, 0.0, self.model_version, "inference_unavailable")
                result = json.loads(response.read())
            prediction = result.get("prediction")
            confidence = result.get("confidence")
            returned_version = result.get("model_version")
            if isinstance(prediction, bool) or not isinstance(prediction, (int, float)):
                return InferenceResult(None, 0.0, self.model_version, "invalid_model_response")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                return InferenceResult(None, 0.0, self.model_version, "invalid_model_response")
            if not isinstance(returned_version, str) or not returned_version.strip() or returned_version != self.model_version:
                return InferenceResult(None, 0.0, self.model_version, "invalid_model_response")
            return InferenceResult(float(prediction), float(confidence), returned_version, "predicted")
        except (HTTPError, URLError, OSError, TimeoutError, ValueError, TypeError, json.JSONDecodeError):
            return InferenceResult(None, 0.0, self.model_version, "inference_unavailable")
