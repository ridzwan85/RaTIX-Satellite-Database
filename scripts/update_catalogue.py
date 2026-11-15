#!/usr/bin/env python3
"""Fetch, validate and publish versioned CelesTrak GP JSON snapshots."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SOURCE_URL = "https://celestrak.org/NORAD/elements/gp.php?GROUP=active&FORMAT=json"
USER_AGENT = "RaTIX-Satellite-Database/1.0 (+https://github.com/ridzwan85/RaTIX-Satellite-Database)"
REQUIRED_FIELDS = (
    "OBJECT_NAME", "NORAD_CAT_ID", "EPOCH", "MEAN_MOTION",
    "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
    "ARG_OF_PERICENTER", "MEAN_ANOMALY",
)
SNAPSHOT_RE = re.compile(r"^active-(\d{8}T\d{6}Z)\.json$")


class CatalogueError(Exception):
    """Raised when upstream data cannot safely be published."""


def parse_epoch(value: Any) -> datetime:
    if not isinstance(value, str):
        raise CatalogueError("EPOCH must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CatalogueError(f"Invalid EPOCH: {value!r}") from exc
    if parsed.tzinfo is None:
        raise CatalogueError(f"EPOCH has no timezone: {value!r}")
    return parsed.astimezone(timezone.utc)


def validate_catalogue(records: Any) -> tuple[list[dict[str, Any]], str]:
    if not isinstance(records, list) or not records:
        raise CatalogueError("Expected a non-empty JSON array")
    seen: set[int] = set()
    clean: list[dict[str, Any]] = []
    newest_epoch: datetime | None = None
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise CatalogueError(f"Record {index} is not a JSON object")
        missing = [field for field in REQUIRED_FIELDS if field not in record]
        if missing:
            raise CatalogueError(f"Record {index} missing fields: {', '.join(missing)}")
        if not isinstance(record["OBJECT_NAME"], str) or not record["OBJECT_NAME"].strip():
            raise CatalogueError(f"Record {index} has an invalid OBJECT_NAME")
        try:
            norad_id = int(record["NORAD_CAT_ID"])
            mean_motion = float(record["MEAN_MOTION"])
            eccentricity = float(record["ECCENTRICITY"])
            inclination = float(record["INCLINATION"])
            raan = float(record["RA_OF_ASC_NODE"])
            arg_perigee = float(record["ARG_OF_PERICENTER"])
            mean_anomaly = float(record["MEAN_ANOMALY"])
        except (TypeError, ValueError) as exc:
            raise CatalogueError(f"Record {index} has invalid numeric fields") from exc
        if norad_id <= 0:
            raise CatalogueError(f"Record {index} has a non-positive NORAD_CAT_ID")
        if norad_id in seen:
            raise CatalogueError(f"Duplicate NORAD_CAT_ID: {norad_id}")
        if mean_motion <= 0:
            raise CatalogueError(f"Record {index} has non-positive MEAN_MOTION")
        if not 0.0 <= eccentricity < 1.0:
            raise CatalogueError(f"Record {index} has invalid ECCENTRICITY")
        if not 0.0 <= inclination <= 180.0:
            raise CatalogueError(f"Record {index} has invalid INCLINATION")
        if not 0.0 <= raan <= 360.0 or not 0.0 <= arg_perigee <= 360.0:
            raise CatalogueError(f"Record {index} has invalid angular orbital elements")
        if not 0.0 <= mean_anomaly <= 360.0:
            raise CatalogueError(f"Record {index} has invalid MEAN_ANOMALY")
        epoch = parse_epoch(record["EPOCH"])
        newest_epoch = epoch if newest_epoch is None else max(newest_epoch, epoch)
        seen.add(norad_id)
        clean.append(record)
    assert newest_epoch is not None
    return clean, newest_epoch.isoformat().replace("+00:00", "Z")


def download_json(url: str = SOURCE_URL, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urlopen(request, timeout=90) as response:
                if response.status != 200:
                    raise CatalogueError(f"Upstream returned HTTP {response.status}")
                payload = response.read()
            if not payload:
                raise CatalogueError("Upstream returned an empty response")
            return payload
        except (HTTPError, URLError, TimeoutError, CatalogueError) as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(2 ** attempt)
    raise CatalogueError(f"Unable to fetch CelesTrak data after {attempts} attempts: {last_error}")


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def prune_snapshots(root: Path, keep: int = 10) -> None:
    data_dir = root / "data"
    if not data_dir.exists():
        return
    snapshots = []
    for path in data_dir.glob("active-*.json"):
        match = SNAPSHOT_RE.match(path.name)
        if match:
            snapshots.append((match.group(1), path))
    snapshots.sort(reverse=True)
    for _, path in snapshots[keep:]:
        path.unlink(missing_ok=True)


def publish(payload: bytes, root: Path) -> dict[str, Any]:
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogueError(f"Upstream response is not valid UTF-8 JSON: {exc}") from exc
    records, newest_epoch = validate_catalogue(decoded)
    digest = hashlib.sha256(payload).hexdigest()
    manifest_path = root / "latest.json"
    if manifest_path.exists():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
            if previous.get("sha256") == digest:
                print(f"Catalogue unchanged ({len(records)} records, sha256 {digest})")
                return previous
        except (OSError, json.JSONDecodeError, AttributeError):
            pass

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    relative_file = f"data/active-{stamp}.json"
    atomic_write(root / relative_file, payload)
    manifest = {
        "schema_version": 1,
        "updated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "source": "CelesTrak GP active group",
        "source_url": SOURCE_URL,
        "format": "CelesTrak GP JSON",
        "file": relative_file,
        "sha256": digest,
        "record_count": len(records),
        "latest_epoch_utc": newest_epoch,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write(manifest_path, manifest_bytes)
    prune_snapshots(root, keep=10)
    print(f"Published {len(records)} records to {relative_file}; sha256={digest}")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--input", type=Path, help="Use a local JSON fixture instead of fetching CelesTrak")
    args = parser.parse_args()
    try:
        payload = args.input.read_bytes() if args.input else download_json()
        publish(payload, args.root)
    except (OSError, CatalogueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
