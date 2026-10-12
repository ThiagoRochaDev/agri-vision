import json
import base64
import hashlib
import logging
import struct
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from production_check import check
from agri_vision.api import MAX_REQUEST_BYTES, handler_for
from agri_vision.store import Store


def png_fixture(width: int = 1280, height: int = 720, suffix: bytes = b"fixture") -> bytes:
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00\x00\x00\x00\x00" + suffix


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = Store(":memory:")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.store, "secret-key"))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.store.close()

    def request(self, path: str, payload: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(self.base_url + path, data=body, headers=headers or {}, method="POST" if body else "GET")
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())
        return response.status, json.loads(response.read())

    def test_health_is_public_but_data_requires_api_key(self) -> None:
        health_request = urllib.request.Request(self.base_url + "/health", headers={"X-Request-ID": "health-check-1"})
        with self.assertLogs("agri_vision.http", level=logging.INFO) as logs:
            health_response = urllib.request.urlopen(health_request)
        self.assertEqual(health_response.status, 200)
        self.assertEqual(health_response.headers["X-Request-ID"], "health-check-1")
        self.assertEqual(health_response.headers["X-Content-Type-Options"], "nosniff")
        self.assertTrue(any("request_id=health-check-1" in message for message in logs.output))
        metrics_response = urllib.request.urlopen(self.base_url + "/metrics")
        self.assertIn(b"agri_vision_requests_total", metrics_response.read())
        self.assertEqual(self.request("/farms", {"name": "x", "region": "SP"})[0], 401)
        status, farm = self.request("/farms", {"name": "x", "region": "SP"}, {"X-API-Key": "secret-key", "X-Organization-ID": "org-a"})
        self.assertEqual(status, 201)
        self.assertEqual(farm["organization_id"], "org-a")
        self.assertEqual(check(self.base_url, "secret-key"), [])
        self.assertEqual(check(self.base_url), ["api_key_missing"])
        self.assertEqual(check(self.base_url, allow_unauthenticated=True), [])

    def test_ready_fails_when_media_directory_is_not_available(self) -> None:
        self.store.media_dir = Path(self.store.media_dir) / "missing-media-directory"
        status, body = self.request("/ready")
        self.assertEqual(status, 503)
        self.assertEqual(body["status"], "not_ready")

    def test_report_csv_requires_authentication(self) -> None:
        self.assertEqual(self.request("/plots/unknown/reports.csv")[0], 401)

    def test_post_authentication_precedes_payload_parsing(self) -> None:
        request = urllib.request.Request(self.base_url + "/farms", data=b"not-json", method="POST")
        with self.assertRaises(urllib.error.HTTPError) as context:
            urllib.request.urlopen(request)
        self.assertEqual(context.exception.code, 401)

    def test_api_exposes_stable_domain_error_statuses(self) -> None:
        headers = {"X-API-Key": "secret-key", "X-Organization-ID": "org-errors"}
        self.assertEqual(self.request("/plots/missing", {"name": "x"}, headers)[0], 404)
        status, _ = self.request("/plots", [], headers)
        self.assertEqual(status, 400)
        status, _ = self.request("/campaigns/missing/transition", {"status": "closed"}, headers)
        self.assertEqual(status, 404)

    def test_protected_flow_runs_from_farm_to_report(self) -> None:
        headers = {"X-API-Key": "secret-key", "X-Organization-ID": "org-flow", "X-Actor-ID": "operator"}
        status, farm = self.request("/farms", {"name": "Fazenda API", "region": "SP"}, headers)
        self.assertEqual(status, 201)
        status, plot = self.request("/plots", {"farm_id": farm["id"], "name": "Talhão API", "crop": "café"}, headers)
        self.assertEqual(status, 201)
        status, campaign = self.request("/campaigns", {"plot_id": plot["id"], "protocol_version": "v1", "captured_period": "2026-10", "task": "contagem de frutos"}, headers)
        self.assertEqual(status, 201)
        sample_payload = {"client_event_id": "api-flow-1", "content_hash": "flow-hash", "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05}}
        status, sample = self.request(f"/campaigns/{campaign['id']}/samples", sample_payload, headers)
        self.assertEqual(status, 201)
        status, review = self.request(f"/observations/{sample['observation_id']}/reviews", {"prediction": 8, "note": "conferido", "reviewer": "operator"}, headers)
        self.assertEqual(status, 200)
        status, report = self.request(f"/plots/{plot['id']}/reports", headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(report["campaigns"][0]["reviewed_count"], 1)
        status, coverage = self.request(f"/plots/{plot['id']}/coverage", headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(coverage["located_count"], 1)
        self.assertFalse(coverage["extrapolation_allowed"])

    def test_sync_batch_is_idempotent_and_conflicts_are_explicit(self) -> None:
        headers = {"X-API-Key": "secret-key", "X-Organization-ID": "org-sync"}
        _, farm = self.request("/farms", {"name": "Fazenda sync", "region": "SP"}, headers)
        _, plot = self.request("/plots", {"farm_id": farm["id"], "name": "Talhão sync", "crop": "café"}, headers)
        _, campaign = self.request("/campaigns", {"plot_id": plot["id"], "protocol_version": "v1", "captured_period": "2026-10", "task": "contagem"}, headers)
        event = {"campaign_id": campaign["id"], "client_event_id": "offline-1", "content_hash": "offline-hash", "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05}}
        status, first = self.request("/sync-batches", {"events": [event]}, headers)
        self.assertEqual(status, 200)
        status, repeated = self.request("/sync-batches", {"events": [event]}, headers)
        self.assertEqual(status, 200)
        self.assertEqual(first["items"][0]["id"], repeated["items"][0]["id"])
        conflict = dict(event, content_hash="different-hash")
        status, body = self.request("/sync-batches", {"events": [conflict]}, headers)
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "client_event_conflict")

    def test_duplicate_model_version_is_a_conflict(self) -> None:
        headers = {"X-API-Key": "secret-key", "X-Organization-ID": "org-model"}
        dataset_payload = {"name": "dataset", "provenance": "pilot", "consent_scope": "internal", "split_definition": {"group_by": "property", "evaluation_groups": ["reserve"]}}
        status, dataset = self.request("/dataset-versions", dataset_payload, headers)
        self.assertEqual(status, 201)
        model_payload = {"version": "model-1", "task": "contagem", "artifact_sha256": "a" * 64, "dataset_version_id": dataset["id"], "status": "validated"}
        self.assertEqual(self.request("/model-versions", model_payload, headers)[0], 201)
        status, body = self.request("/model-versions", model_payload, headers)
        self.assertEqual(status, 409)
        self.assertIn("UNIQUE", body["error"])
        status, _ = self.request("/dataset-versions", dict(dataset_payload, name="dataset-after-conflict"), headers)
        self.assertEqual(status, 201)

    def test_sample_upload_does_not_expose_filesystem_path(self) -> None:
        headers = {"X-API-Key": "secret-key", "X-Organization-ID": "org-media"}
        _, farm = self.request("/farms", {"name": "Fazenda mídia", "region": "SP"}, headers)
        _, plot = self.request("/plots", {"farm_id": farm["id"], "name": "Talhão", "crop": "café"}, headers)
        _, campaign = self.request("/campaigns", {"plot_id": plot["id"], "protocol_version": "v1", "captured_period": "2026-10", "task": "contagem"}, headers)
        media = png_fixture(suffix=b"private-image")
        payload = {
            "client_event_id": "media-api-1",
            "content_hash": hashlib.sha256(media).hexdigest(),
            "media_base64": base64.b64encode(media).decode(),
            "capture_metadata": {"width": 1280, "height": 720, "blur_score": 0.9, "crop": "café", "latitude": -23.05, "longitude": -47.05},
        }
        status, sample = self.request(f"/campaigns/{campaign['id']}/samples", payload, headers)
        self.assertEqual(status, 201)
        self.assertNotIn("media_path", sample)

    def test_request_budget_can_carry_the_allowed_media_size(self) -> None:
        encoded_size = len(base64.b64encode(b"x" * (6 * 1024 * 1024)))
        self.assertLess(encoded_size + 1024 * 1024, MAX_REQUEST_BYTES)


if __name__ == "__main__":
    unittest.main()
