from __future__ import annotations

import argparse
import json
import shutil
import struct
import sys
from pathlib import Path
from typing import Any


LABELS = {"immature apple": 0, "semi-mature apple": 1, "mature apple": 2}
SPLITS = ("train", "val", "test")


def jpeg_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:2] != b"\xff\xd8":
        raise ValueError(f"not_jpeg:{path}")
    position = 2
    while position + 9 < len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        marker = data[position + 1]
        position += 2
        if marker in {0xD8, 0xD9}:
            continue
        if position + 2 > len(data):
            break
        segment_length = struct.unpack(">H", data[position : position + 2])[0]
        if marker in set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0)):
            if position + 7 > len(data):
                break
            height, width = struct.unpack(">HH", data[position + 3 : position + 7])
            return width, height
        position += segment_length
    raise ValueError(f"jpeg_dimensions_missing:{path}")


def _load_annotations(path: Path) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in json.loads(path.read_text(encoding="utf-8")).values():
        if isinstance(item, dict) and isinstance(item.get("filename"), str):
            grouped.setdefault(item["filename"], []).append(item)
    return grouped


def _select_annotation(image: Path, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    matching = [item for item in candidates if item.get("size") == image.stat().st_size]
    if len(matching) == 1:
        return matching[0]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(f"annotation_size_ambiguous:{image.name}")


def convert(root: str | Path, output: str | Path, resolution: str = "original") -> int:
    source_root = Path(root).resolve()
    destination = Path(output).resolve()
    suffix = "_resize" if resolution == "resize" else ""
    total = 0
    for split in SPLITS:
        source_dir = source_root / f"{split}{suffix}"
        annotation_path = source_root / f"{split}{suffix}.json"
        images_dir = destination / "images" / split
        labels_dir = destination / "labels" / split
        images_dir.mkdir(parents=True, exist_ok=True)
        labels_dir.mkdir(parents=True, exist_ok=True)
        annotations = _load_annotations(annotation_path)
        for image in sorted(source_dir.iterdir()):
            if image.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            width, height = jpeg_dimensions(image)
            annotation = _select_annotation(image, annotations.get(image.name, []))
            lines: list[str] = []
            for region in annotation.get("regions") or []:
                attributes = region.get("region_attributes", {})
                label = attributes.get("name") if isinstance(attributes, dict) else None
                shape = region.get("shape_attributes", {})
                x_points = shape.get("all_points_x", []) if isinstance(shape, dict) else []
                y_points = shape.get("all_points_y", []) if isinstance(shape, dict) else []
                if label not in LABELS or len(x_points) != len(y_points) or len(x_points) < 3:
                    continue
                coordinates = []
                for x, y in zip(x_points, y_points):
                    coordinates.extend((max(0.0, min(1.0, float(x) / width)), max(0.0, min(1.0, float(y) / height))))
                lines.append(" ".join([str(LABELS[label]), *(f"{value:.6f}" for value in coordinates)]))
            shutil.copy2(image, images_dir / image.name)
            (labels_dir / f"{image.stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            total += 1
    (destination / "dataset.yaml").write_text(
        f"path: {destination.as_posix()}\ntrain: images/train\nval: images/val\ntest: images/test\n"
        "names:\n  0: immature apple\n  1: semi-mature apple\n  2: mature apple\n",
        encoding="utf-8",
    )
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert the external VIA dataset to YOLO segmentation format")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--resolution", choices=["original", "resize"], default="original")
    args = parser.parse_args()
    try:
        total = convert(args.root, args.output, args.resolution)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL {error}")
        return 1
    print(f"converted={total} output={args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
