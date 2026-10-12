from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SPLITS = {"train": "train", "val": "evaluation", "test": "evaluation"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_annotations(path: Path) -> dict[str, list[dict[str, Any]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in raw.values():
        if not isinstance(item, dict) or not isinstance(item.get("filename"), str):
            continue
        grouped.setdefault(item["filename"], []).append(item)
    return grouped


def _annotation_for(image: Path, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    matching = [item for item in candidates if item.get("size") == image.stat().st_size]
    if len(matching) == 1:
        return matching[0]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(f"annotation_size_ambiguous:{image.name}")


def convert(root: str | Path, dataset_version_id: str, resolution: str = "original") -> list[dict[str, Any]]:
    dataset_root = Path(root).resolve()
    suffix = "_resize" if resolution == "resize" else ""
    result: list[dict[str, Any]] = []
    for source_split, output_split in SPLITS.items():
        folder = dataset_root / f"{source_split}{suffix}"
        annotation_path = dataset_root / f"{source_split}{suffix}.json"
        if not folder.is_dir():
            raise ValueError(f"split_missing:{folder}")
        if not annotation_path.is_file():
            raise ValueError(f"annotation_missing:{annotation_path}")
        annotations = _load_annotations(annotation_path)
        for image in sorted(folder.iterdir()):
            if image.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                continue
            candidates = annotations.get(image.name, [])
            if not candidates:
                raise ValueError(f"annotation_missing:{image.name}")
            annotation = _annotation_for(image, candidates)
            regions = annotation.get("regions") or []
            labels = sorted(
                {
                    region.get("region_attributes", {}).get("name")
                    for region in regions
                    if isinstance(region, dict) and isinstance(region.get("region_attributes"), dict)
                    and isinstance(region.get("region_attributes", {}).get("name"), str)
                }
            )
            result.append(
                {
                    "sample_id": f"apple-maturity-{source_split}-{image.stem}",
                    "media_path": str(image),
                    "content_hash": _sha256(image),
                    "capture_metadata": {
                        "crop": "apple",
                        "source": "external_dataset",
                        "source_dataset_id": "apple-maturity-gfcmdbvw65-v4",
                        "annotation_format": "VIA",
                        "research_only": True,
                    },
                    "group": f"apple-maturity:{source_split}",
                    "split": output_split,
                    "dataset_version_id": dataset_version_id,
                    "quality_status": "external_unreviewed",
                    "external_annotation": {
                        "source_file": str(annotation_path),
                        "filename": annotation.get("filename"),
                        "region_count": len(regions),
                        "labels": labels,
                        "regions": regions,
                    },
                }
            )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert the external VIA dataset to Agri Vision JSONL")
    parser.add_argument("--root", required=True, type=Path, help="Extracted dataset-20260508 directory")
    parser.add_argument("--dataset-version-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--resolution", choices=["original", "resize"], default="original")
    args = parser.parse_args()
    try:
        rows = convert(args.root, args.dataset_version_id, args.resolution)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL {error}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"converted={len(rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
