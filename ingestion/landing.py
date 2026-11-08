"""Bronze writer: one raw JSON document per API object, never edited after it is final."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("F1_DATA_DIR", "data"))


def bronze_path(source: str, endpoint: str, **partitions: object) -> Path:
    """Hive-style path, e.g. bronze/jolpica/results/season=2023/round=01.json."""
    parts = [f"{key}={value}" for key, value in partitions.items()]
    *dirs, leaf = parts
    return DATA_DIR / "bronze" / source / endpoint / Path(*dirs) / f"{leaf}.json"


def write_bronze(path: Path, payload: Any, source_url: str) -> None:
    """Write atomically, so a crash mid-write never leaves a half file that looks final."""
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_url": source_url,
        "payload": payload,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(envelope, ensure_ascii=False))
    tmp.replace(path)


def read_bronze(path: Path) -> Any:
    """Return the payload of a bronze file."""
    return json.loads(path.read_text())["payload"]


def is_final(path: Path, settled_at: datetime) -> bool:
    """True when the file was fetched after the data settled, so it never needs refetching.

    Stewards can still change results for a few days after a race, which is why callers
    pass a `settled_at` some days after the session rather than the session time itself.
    """
    if not path.exists():
        return False
    fetched_at = datetime.fromisoformat(json.loads(path.read_text())["fetched_at"])
    return fetched_at >= settled_at
