from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def create_backup(database: str, media_dir: str, output: str) -> Path:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_output: Path | None = None
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        temporary_output = Path(temporary) / destination.name
        snapshot = Path(temporary) / "agri_vision.sqlite3"
        source = sqlite3.connect(database)
        target = sqlite3.connect(snapshot)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        with zipfile.ZipFile(temporary_output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            manifest: dict[str, str] = {}
            archive.write(snapshot, "agri_vision.sqlite3")
            manifest["agri_vision.sqlite3"] = _sha256(snapshot)
            media_root = Path(media_dir)
            if media_root.exists():
                for media_file in media_root.rglob("*"):
                    if media_file.is_file():
                        member = str(Path("media") / media_file.relative_to(media_root))
                        archive.write(media_file, member)
                        manifest[member] = _sha256(media_file)
            archive.writestr("MANIFEST.sha256.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
        os.replace(temporary_output, destination)
    return destination


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a consistent Agri Vision backup")
    parser.add_argument("--database", default="agri_vision.sqlite3")
    parser.add_argument("--media-dir", default="media")
    parser.add_argument("--output", default=f"backups/agri-vision-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.zip")
    args = parser.parse_args()
    print(create_backup(args.database, args.media_dir, args.output))


if __name__ == "__main__":
    main()
