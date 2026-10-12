from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path


def _safe_member(root: Path, member: str) -> Path:
    destination = (root / member).resolve()
    if root.resolve() not in destination.parents and destination != root.resolve():
        raise ValueError("unsafe_backup_path")
    return destination


def restore_backup(backup: str, target_dir: str) -> Path:
    destination = Path(target_dir)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("restore_target_must_be_empty")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        staging = Path(temporary) / "staging"
        staging.mkdir()
        with zipfile.ZipFile(backup) as archive:
            try:
                manifest = json.loads(archive.read("MANIFEST.sha256.json"))
            except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as error:
                raise ValueError("backup_manifest_missing_or_invalid") from error
            if not isinstance(manifest, dict) or "agri_vision.sqlite3" not in manifest:
                raise ValueError("backup_manifest_invalid")
            manifest_members = set(manifest)
            archive_members = {member.filename for member in archive.infolist() if member.filename != "MANIFEST.sha256.json"}
            if archive_members != manifest_members or any(not isinstance(value, str) for value in manifest.values()):
                raise ValueError("backup_manifest_members_mismatch")
            for member in archive.infolist():
                _safe_member(staging, member.filename)
            archive.extractall(staging)
            for member, expected_hash in manifest.items():
                member_path = _safe_member(staging, member)
                if not member_path.is_file() or _sha256(member_path) != expected_hash:
                    raise ValueError(f"backup_integrity_mismatch:{member}")
        for source in staging.iterdir():
            target = destination / source.name
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
    return destination


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore an Agri Vision backup into an empty directory")
    parser.add_argument("backup")
    parser.add_argument("target_dir")
    args = parser.parse_args()
    print(restore_backup(args.backup, args.target_dir))


if __name__ == "__main__":
    main()
