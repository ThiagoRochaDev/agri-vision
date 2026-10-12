import json
import tempfile
import unittest
from pathlib import Path

from external_dataset_to_jsonl import convert


class ExternalDatasetConversionTests(unittest.TestCase):
    def test_convert_preserves_annotations_and_creates_explicit_evaluation_split(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "train").mkdir()
            (root / "val").mkdir()
            (root / "test").mkdir()
            for split, name in (("train", "train.jpg"), ("val", "val.jpg"), ("test", "test.jpg")):
                image = root / split / name
                image.write_bytes(b"image-" + split.encode())
                annotation = {
                    f"{name}{image.stat().st_size}": {
                        "filename": name,
                        "size": image.stat().st_size,
                        "regions": [{"region_attributes": {"name": "mature apple"}}],
                    }
                }
                (root / f"{split}.json").write_text(json.dumps(annotation), encoding="utf-8")
            rows = convert(root, "dataset-1")
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0]["split"], "evaluation" if rows[0]["group"].endswith((":val", ":test")) else "train")
            self.assertTrue(all(row["quality_status"] == "external_unreviewed" for row in rows))
            self.assertEqual(rows[0]["external_annotation"]["labels"], ["mature apple"])

    def test_resize_layout_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for split in ("train", "val", "test"):
                folder = root / f"{split}_resize"
                folder.mkdir()
                image = folder / f"{split}.jpg"
                image.write_bytes(b"resize-" + split.encode())
                annotation = {f"{image.name}{image.stat().st_size}": {"filename": image.name, "size": image.stat().st_size, "regions": []}}
                (root / f"{split}_resize.json").write_text(json.dumps(annotation), encoding="utf-8")
            self.assertEqual(len(convert(root, "dataset-1", "resize")), 3)
