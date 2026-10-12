from __future__ import annotations

import argparse
import json

from agri_vision.config import Settings
from agri_vision.store import Store


def main() -> None:
    settings = Settings.from_environment()
    parser = argparse.ArgumentParser(description="Export an explicit Agri Vision train/evaluation split")
    parser.add_argument("--dataset-version-id", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--organization-id", default="default")
    args = parser.parse_args()
    store = Store(settings.database, settings.media_dir)
    try:
        rows = store.export_dataset(args.dataset_version_id, args.organization_id)
    finally:
        store.close()
    with open(args.output, "w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"exported={len(rows)} output={args.output}")


if __name__ == "__main__":
    main()
