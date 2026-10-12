from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from agri_vision.config import Settings
from agri_vision.store import Store


def main() -> None:
    settings = Settings.from_environment()
    parser = argparse.ArgumentParser(description="Preview or execute Agri Vision sample retention")
    parser.add_argument("--days", type=int, required=True)
    parser.add_argument("--organization-id", default="default")
    parser.add_argument("--actor", default="retention-job")
    parser.add_argument("--execute", action="store_true", help="actually delete expired samples")
    args = parser.parse_args()
    if args.days < 1:
        raise SystemExit("--days must be positive")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)).isoformat()
    store = Store(settings.database, settings.media_dir)
    try:
        print(store.purge_samples_before(cutoff, args.organization_id, args.execute, args.actor))
    finally:
        store.close()


if __name__ == "__main__":
    main()
