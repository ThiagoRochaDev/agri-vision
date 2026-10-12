from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_TEXT_FIELDS = {
    "crop": "crop_missing",
    "task": "task_missing",
    "partner": "partner_missing",
    "protocol_version": "protocol_version_missing",
    "annotation_owner": "annotation_owner_missing",
    "baseline": "baseline_missing",
    "consent_scope": "consent_scope_missing",
    "review_protocol": "review_protocol_missing",
}


def _is_real_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and "preencher" not in value.lower()


def validate(config: dict[str, Any]) -> list[str]:
    failures = [error for field, error in REQUIRED_TEXT_FIELDS.items() if not _is_real_text(config.get(field))]
    evaluation_groups = config.get("evaluation_groups")
    if not isinstance(evaluation_groups, list) or not evaluation_groups or any(not _is_real_text(group) for group in evaluation_groups):
        failures.append("evaluation_groups_missing_or_invalid")
    data_source = config.get("data_source")
    if not _is_real_text(data_source):
        failures.append("data_source_missing")
    if config.get("extrapolation_allowed") is not False:
        failures.append("extrapolation_must_remain_false")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the agronomic pilot gate")
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL config_invalid:{error}")
        return 1
    if not isinstance(config, dict):
        print("FAIL config_must_be_object")
        return 1
    failures = validate(config)
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    print("OK pilot gate")
    return 0


if __name__ == "__main__":
    sys.exit(main())
