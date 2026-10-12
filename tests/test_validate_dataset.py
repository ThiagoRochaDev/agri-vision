import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from validate_dataset import validate


class DatasetValidationTests(unittest.TestCase):
    def test_exported_dataset_with_train_and_evaluation_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            media = Path(temporary) / "sample.jpg"
            media.write_bytes(b"image")
            item = {
                "sample_id": "sample-1",
                "media_path": str(media),
                "content_hash": hashlib.sha256(b"image").hexdigest(),
                "capture_metadata": {"crop": "café"},
                "group": "farm-a",
                "split": "train",
                "dataset_version_id": "dataset-1",
            }
            evaluation = dict(item, sample_id="sample-2", group="farm-reserve", split="evaluation")
            dataset = Path(temporary) / "dataset.jsonl"
            dataset.write_text("\n".join(json.dumps(row) for row in (item, evaluation)), encoding="utf-8")
            self.assertEqual(validate(dataset), [])

    def test_invalid_hash_and_missing_evaluation_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            dataset = Path(temporary) / "dataset.jsonl"
            dataset.write_text(json.dumps({"sample_id": "x", "media_path": "missing.jpg", "content_hash": "0" * 64, "capture_metadata": {}, "group": "farm-a", "split": "train", "dataset_version_id": "dataset-1", "quality_status": "rejected"}), encoding="utf-8")
            failures = validate(dataset)
            self.assertIn("line_1:rejected_sample", failures)
            self.assertIn("line_1:media_missing", failures)
            self.assertIn("evaluation_split_empty", failures)
