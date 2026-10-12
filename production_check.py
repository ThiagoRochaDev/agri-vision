from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request


def check(base_url: str, api_key: str | None = None, *, allow_unauthenticated: bool = False) -> list[str]:
    failures: list[str] = []
    if not api_key and not allow_unauthenticated:
        failures.append("api_key_missing")
    for path in ("/health", "/ready"):
        request = urllib.request.Request(base_url.rstrip("/") + path)
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                if response.status != 200:
                    failures.append(f"{path}:status_{response.status}")
        except (urllib.error.URLError, TimeoutError) as error:
            failures.append(f"{path}:unreachable:{error}")
    metrics_request = urllib.request.Request(base_url.rstrip("/") + "/metrics")
    if api_key:
        metrics_request.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(metrics_request, timeout=5) as response:
            body = response.read().decode("utf-8")
            if response.status != 200 or "agri_vision_requests_total" not in body:
                failures.append("/metrics:invalid")
    except (urllib.error.URLError, TimeoutError) as error:
        failures.append(f"/metrics:unreachable:{error}")
    if api_key:
        protected_url = base_url.rstrip("/") + "/dataset-versions"
        try:
            with urllib.request.urlopen(urllib.request.Request(protected_url), timeout=5) as response:
                failures.append(f"/dataset-versions:expected_401_got_{response.status}")
        except urllib.error.HTTPError as error:
            if error.code != 401:
                failures.append(f"/dataset-versions:expected_401_got_{error.code}")
        except (urllib.error.URLError, TimeoutError) as error:
            failures.append(f"/dataset-versions:unreachable:{error}")
        authorized_request = urllib.request.Request(protected_url, headers={"X-API-Key": api_key})
        try:
            with urllib.request.urlopen(authorized_request, timeout=5) as response:
                if response.status != 200:
                    failures.append(f"/dataset-versions:authorized_status_{response.status}")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            failures.append(f"/dataset-versions:authorized_unreachable:{error}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Check a running Agri Vision deployment")
    parser.add_argument("--url", default=os.getenv("AGRI_VISION_URL", "http://127.0.0.1:8765"))
    parser.add_argument("--api-key", default=os.getenv("AGRI_VISION_API_KEY"))
    parser.add_argument("--allow-unauthenticated", action="store_true", help="permite checagem local sem chave; não usar para liberar produção")
    args = parser.parse_args()
    failures = check(args.url, args.api_key, allow_unauthenticated=args.allow_unauthenticated)
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    print("OK health ready metrics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
