import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agri_vision.inference import HttpInferenceEngine


class InferenceTests(unittest.TestCase):
    def test_http_engine_validates_contract_and_sends_input(self) -> None:
        received: dict = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                received.update(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                body = json.dumps({"prediction": 12.5, "confidence": 0.87, "model_version": "v1"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                media = Path(directory) / "sample.jpg"
                media.write_bytes(b"image-bytes")
                engine = HttpInferenceEngine(f"http://127.0.0.1:{server.server_port}", "v1", "secret", 2)
                result = engine.infer(media, {"crop": "cafe"}, "contagem")
            self.assertEqual(result.status, "predicted")
            self.assertEqual(result.prediction, 12.5)
            self.assertEqual(result.model_version, "v1")
            self.assertEqual(received["task"], "contagem")
            self.assertEqual(received["model_version"], "v1")
            self.assertTrue(received["media_base64"])
        finally:
            server.shutdown()
            server.server_close()

    def test_http_engine_never_fabricates_on_invalid_response_or_missing_input(self) -> None:
        engine = HttpInferenceEngine("http://127.0.0.1:1", "v1", timeout=0.1)
        missing = engine.infer(None, {}, "contagem")
        self.assertEqual(missing.status, "input_missing")
        self.assertIsNone(missing.prediction)

        with tempfile.TemporaryDirectory() as directory:
            media = Path(directory) / "sample.jpg"
            media.write_bytes(b"image-bytes")
            unavailable = engine.infer(media, {}, "contagem")
        self.assertEqual(unavailable.status, "inference_unavailable")
        self.assertIsNone(unavailable.prediction)

    def test_http_engine_rejects_a_response_from_another_model_version(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = json.dumps({"prediction": 12, "confidence": 0.9, "model_version": "v2"}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                media = Path(directory) / "sample.jpg"
                media.write_bytes(b"image-bytes")
                engine = HttpInferenceEngine(f"http://127.0.0.1:{server.server_port}", "v1", timeout=2)
                result = engine.infer(media, {}, "contagem")
            self.assertEqual(result.status, "invalid_model_response")
            self.assertIsNone(result.prediction)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
