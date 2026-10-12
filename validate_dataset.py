from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {"sample_id", "media_path", "content_hash", "capture_metadata", "group", "split", "dataset_version_id"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(path: str | Path) -> list[str]:
    failures: list[str] = []
    counts = {"train": 0, "evaluation": 0}
    source = Path(path)
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        return [f"dataset_unreadable:{error}"]
    if not lines:
        return ["dataset_empty"]
    for line_number, line in enumerate(lines, 1):
        try:
            item: Any = json.loads(line)
        except json.JSONDecodeError:
            failures.append(f"line_{line_number}:invalid_json")
            continue
        if not isinstance(item, dict):
            failures.append(f"line_{line_number}:item_must_be_object")
            continue
        missing = REQUIRED_FIELDS - set(item)
        failures.extend(f"line_{line_number}:missing_{field}" for field in sorted(missing))
        if item.get("quality_status") == "rejected":
            failures.append(f"line_{line_number}:rejected_sample")
        split = item.get("split")
        if split not in counts:
            failures.append(f"line_{line_number}:split_invalid")
        else:
            counts[split] += 1
        media_path = item.get("media_path")
        content_hash = item.get("content_hash")
        if isinstance(media_path, str) and isinstance(content_hash, str):
            media = Path(media_path)
            if not media.is_file():
                failures.append(f"line_{line_number}:media_missing")
            elif _sha256(media) != content_hash.lower():
                failures.append(f"line_{line_number}:content_hash_mismatch")
    if counts["train"] == 0:
        failures.append("train_split_empty")
    if counts["evaluation"] == 0:
        failures.append("evaluation_split_empty")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an exported Agri Vision dataset")
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args()
    failures = validate(args.dataset)
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    print("OK dataset")
    return 0


if __name__ == "__main__":
    sys.exit(main())
