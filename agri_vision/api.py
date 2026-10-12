from __future__ import annotations

import json
import hmac
import logging
import csv
import io
import sqlite3
import uuid
from collections import Counter
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import urlparse

from .inference import InferenceEngine
from .store import Store

MAX_REQUEST_BYTES = 10 * 1024 * 1024
SERVICE_VERSION = "0.2.0"
WEB_INDEX = Path(__file__).with_name("web") / "index.html"


class Metrics:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: Counter[str] = Counter()

    def observe(self, method: str, status: int) -> None:
        with self._lock:
            self._counters[f"requests_total|{method}|{status}"] += 1

    def render(self) -> bytes:
        lines = ["# HELP agri_vision_requests_total HTTP requests handled by the service", "# TYPE agri_vision_requests_total counter"]
        with self._lock:
            values = dict(self._counters)
        for key, value in sorted(values.items()):
            _, method, status = key.split("|")
            lines.append(f'agri_vision_requests_total{{method="{method}",status="{status}"}} {value}')
        return ("\n".join(lines) + "\n").encode("utf-8")


class ApiError(Exception):
    def __init__(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


def required(payload: dict, *fields: str) -> None:
    missing = [field for field in fields if payload.get(field) in (None, "")]
    if missing:
        raise ApiError(f"missing_fields:{','.join(missing)}")


def public_sample(record: dict) -> dict:
    result = dict(record)
    result.pop("media_path", None)
    return result


def error_status(error: Exception, default: int = HTTPStatus.BAD_REQUEST) -> int:
    if isinstance(error, sqlite3.IntegrityError):
        return HTTPStatus.CONFLICT
    if isinstance(error, ApiError):
        return error.status
    code = str(error)
    if code.endswith("_not_found") or code.endswith("_not_found_or_forbidden") or code == "plot_not_found":
        return HTTPStatus.NOT_FOUND
    if code in {"client_event_conflict", "campaign_transition_not_allowed", "campaign_not_collecting", "validated_model_requires_dataset", "validated_model_requires_complete_dataset"}:
        return HTTPStatus.CONFLICT
    if code in {"farm_not_found_or_forbidden", "plot_not_found_or_forbidden", "dataset_version_not_found_or_forbidden"}:
        return HTTPStatus.NOT_FOUND
    return default


def handler_for(store: Store, api_key: str | None = None, metrics: Metrics | None = None, inference_engine: InferenceEngine | None = None) -> type[BaseHTTPRequestHandler]:
    request_metrics = metrics or Metrics()

    class Handler(BaseHTTPRequestHandler):
        def _request_id(self) -> str:
            if hasattr(self, "_resolved_request_id"):
                return self._resolved_request_id
            supplied = self.headers.get("X-Request-ID", "").strip()
            if supplied and len(supplied) <= 128 and all(char.isalnum() or char in "._-" for char in supplied):
                self._resolved_request_id = supplied
            else:
                self._resolved_request_id = uuid.uuid4().hex
            return self._resolved_request_id

        def _headers(self, content_type: str, length: int) -> None:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("X-Request-ID", self._request_id())
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.send_header("Cache-Control", "no-store")

        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self._headers("application/json; charset=utf-8", len(body))
            self.end_headers()
            self.wfile.write(body)
            request_metrics.observe(self.command, status)

        def _send_html(self) -> None:
            body = WEB_INDEX.read_bytes()
            self.send_response(HTTPStatus.OK)
            self._headers("text/html; charset=utf-8", len(body))
            self.end_headers()
            self.wfile.write(body)
            request_metrics.observe(self.command, HTTPStatus.OK)

        def _send_metrics(self) -> None:
            body = request_metrics.render()
            self.send_response(HTTPStatus.OK)
            self._headers("text/plain; version=0.0.4; charset=utf-8", len(body))
            self.end_headers()
            self.wfile.write(body)

        def _send_text(self, status: int, body: str, content_type: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self._headers(content_type, len(encoded))
            self.end_headers()
            self.wfile.write(encoded)
            request_metrics.observe(self.command, status)

        def _payload(self) -> dict:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > MAX_REQUEST_BYTES:
                    raise ApiError("payload_too_large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
                payload = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(payload, dict):
                    raise ApiError("payload_must_be_object")
                return payload
            except (ValueError, json.JSONDecodeError) as exc:
                raise ApiError("invalid_json") from exc

        def _route(self) -> list[str]:
            return [part for part in urlparse(self.path).path.split("/") if part]

        def _organization_id(self) -> str:
            return self.headers.get("X-Organization-ID", "default").strip() or "default"

        def _actor_id(self) -> str:
            return self.headers.get("X-Actor-ID", "anonymous").strip() or "anonymous"

        def _authorized(self) -> bool:
            if not api_key:
                return True
            supplied = self.headers.get("X-API-Key", "")
            if not supplied:
                authorization = self.headers.get("Authorization", "")
                if authorization.lower().startswith("bearer "):
                    supplied = authorization[7:].strip()
            return hmac.compare_digest(supplied, api_key)

        def do_GET(self) -> None:
            try:
                route = self._route()
                if not route or route == ["index.html"]:
                    self._send_html()
                    return
                if route == ["health"]:
                    self._send(HTTPStatus.OK, {"status": "ok", "service": "agri-vision", "version": SERVICE_VERSION})
                    return
                if route == ["ready"]:
                    if not store.is_ready():
                        self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"status": "not_ready", "service": "agri-vision", "version": SERVICE_VERSION})
                        return
                    self._send(HTTPStatus.OK, {"status": "ready", "service": "agri-vision", "version": SERVICE_VERSION})
                    return
                if route == ["metrics"]:
                    self._send_metrics()
                    return
                if not self._authorized():
                    self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                    return
                if route == ["dataset-versions"]:
                    self._send(HTTPStatus.OK, {"items": store.list_dataset_versions(self._organization_id())})
                    return
                if route == ["model-versions"]:
                    self._send(HTTPStatus.OK, {"items": store.list_model_versions(self._organization_id())})
                    return
                if route == ["audit-events"]:
                    self._send(HTTPStatus.OK, {"items": store.list_audit_events(self._organization_id())})
                    return
                if len(route) == 3 and route[0] == "campaigns" and route[2] == "observations":
                    self._send(HTTPStatus.OK, {"items": store.list_observations(route[1], self._organization_id())})
                    return
                if len(route) == 3 and route[0] == "campaigns" and route[2] == "evaluation":
                    self._send(HTTPStatus.OK, store.evaluate_campaign(route[1], self._organization_id()))
                    return
                if len(route) == 3 and route[0] == "observations" and route[2] == "reviews":
                    self._send(HTTPStatus.OK, {"items": store.list_observation_reviews(route[1], self._organization_id())})
                    return
                if len(route) == 3 and route[0] == "plots" and route[2] == "reports":
                    self._send(HTTPStatus.OK, store.report(route[1], self._organization_id()))
                    return
                if len(route) == 3 and route[0] == "plots" and route[2] == "coverage":
                    self._send(HTTPStatus.OK, store.coverage(route[1], self._organization_id()))
                    return
                if len(route) == 3 and route[0] == "plots" and route[2] == "reports.csv":
                    if not self._authorized():
                        self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                        return
                    report = store.report(route[1], self._organization_id())
                    output = io.StringIO()
                    writer = csv.DictWriter(output, fieldnames=["campaign_id", "captured_period", "sample_count", "accepted_sample_count", "reviewed_count", "reviewed_mean", "delta_from_previous", "representativeness", "extrapolation_allowed"])
                    writer.writeheader()
                    for item in report["campaigns"]:
                        campaign = item["campaign"]
                        writer.writerow({"campaign_id": campaign["id"], "captured_period": campaign["captured_period"], "sample_count": item["sample_count"], "accepted_sample_count": item["accepted_sample_count"], "reviewed_count": item["reviewed_count"], "reviewed_mean": item["reviewed_mean"], "delta_from_previous": item["delta_from_previous"], "representativeness": item["representativeness"], "extrapolation_allowed": report["extrapolation_allowed"]})
                    self._send_text(HTTPStatus.OK, output.getvalue(), "text/csv; charset=utf-8")
                    return
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            except (ApiError, ValueError) as exc:
                self._send(error_status(exc, HTTPStatus.NOT_FOUND), {"error": str(exc)})

        def do_POST(self) -> None:
            try:
                route = self._route()
                if not self._authorized():
                    self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                    return
                payload = self._payload()
                organization_id = self._organization_id()
                actor_id = self._actor_id()
                if route == ["farms"]:
                    required(payload, "name", "region")
                    self._send(HTTPStatus.CREATED, store.create_farm(payload["name"], payload["region"], organization_id, actor_id))
                    return
                if route == ["dataset-versions"]:
                    required(payload, "name", "provenance", "consent_scope", "split_definition")
                    self._send(HTTPStatus.CREATED, store.create_dataset_version(payload["name"], payload["provenance"], payload["consent_scope"], payload["split_definition"], organization_id, actor_id))
                    return
                if route == ["model-versions"]:
                    required(payload, "version", "task", "artifact_sha256", "status")
                    self._send(HTTPStatus.CREATED, store.create_model_version(payload["version"], payload["task"], payload["artifact_sha256"], payload.get("dataset_version_id"), payload["status"], organization_id, actor_id))
                    return
                if route == ["plots"]:
                    required(payload, "farm_id", "name", "crop")
                    self._send(HTTPStatus.CREATED, store.create_plot(payload["farm_id"], payload["name"], payload["crop"], payload.get("geometry"), organization_id, actor_id))
                    return
                if route == ["campaigns"]:
                    required(payload, "plot_id", "protocol_version", "captured_period", "task")
                    self._send(HTTPStatus.CREATED, store.create_campaign(payload["plot_id"], payload["protocol_version"], payload["captured_period"], payload["task"], organization_id, actor_id))
                    return
                if len(route) == 3 and route[0] == "campaigns" and route[2] == "samples":
                    required(payload, "client_event_id", "content_hash", "capture_metadata")
                    self._send(HTTPStatus.CREATED, public_sample(store.add_sample(route[1], payload, organization_id, actor_id)))
                    return
                if len(route) == 3 and route[0] == "campaigns" and route[2] == "transition":
                    required(payload, "status")
                    self._send(HTTPStatus.OK, store.transition_campaign(route[1], payload["status"], organization_id, actor_id))
                    return
                if len(route) == 3 and route[0] == "campaigns" and route[2] == "inference":
                    self._send(HTTPStatus.OK, {"items": store.run_inference(route[1], engine=inference_engine, organization_id=organization_id)})
                    return
                if route == ["sync-batches"]:
                    events = payload.get("events")
                    if not isinstance(events, list):
                        raise ApiError("events_must_be_array")
                    results = [public_sample(store.add_sample(event["campaign_id"], event, organization_id, actor_id)) for event in events]
                    self._send(HTTPStatus.OK, {"items": results})
                    return
                if len(route) == 3 and route[0] == "observations" and route[2] == "reviews":
                    required(payload, "prediction", "note", "reviewer")
                    self._send(HTTPStatus.OK, store.review_observation(route[1], float(payload["prediction"]), payload["note"], payload["reviewer"], organization_id))
                    return
                self._send(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            except (ApiError, ValueError, KeyError, TypeError, sqlite3.IntegrityError) as exc:
                if isinstance(exc, sqlite3.IntegrityError):
                    store.connection.rollback()
                self._send(error_status(exc), {"error": str(exc)})

        def log_message(self, format: str, *args: object) -> None:
            logging.getLogger("agri_vision.http").info("%s %s request_id=%s", self.command, self.path.split("?", 1)[0], self._request_id())

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765, database: str = "agri_vision.sqlite3", media_dir: str = "media", api_key: str | None = None, inference_engine: InferenceEngine | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    store = Store(database, media_dir)
    server = ThreadingHTTPServer((host, port), handler_for(store, api_key, inference_engine=inference_engine))
    print(f"Agri Vision listening on http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        store.close()
