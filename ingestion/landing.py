"""Storage for bronze and silver: a local folder or an s3:// prefix, with one code path.

F1_DATA_DIR picks the root: `data` locally, `s3://<bucket>` in Lambda.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

import pyarrow.fs as pafs


class Storage:
    """A root folder on the local disk or in S3. Paths are '/'-joined strings under it."""

    def __init__(self, root: str) -> None:
        if root.startswith("s3://"):
            self.fs, self.base = pafs.FileSystem.from_uri(root)
            self.local = False
        else:
            self.fs, self.base = pafs.LocalFileSystem(), str(Path(root).resolve())
            self.local = True
        self.base = self.base.rstrip("/")

    def path(self, *parts: str) -> str:
        return "/".join([self.base, *parts])

    def exists(self, path: str) -> bool:
        return self.fs.get_file_info(path).type == pafs.FileType.File

    def read_bytes(self, path: str) -> bytes:
        with self.fs.open_input_stream(path) as stream:
            return stream.read()

    def write_bytes(self, path: str, data: bytes) -> None:
        """S3 puts are atomic; locally write a temp file and rename, so readers never see half."""
        if not self.local:
            with self.fs.open_output_stream(path) as stream:
                stream.write(data)
            return
        self.fs.create_dir(path.rsplit("/", 1)[0], recursive=True)
        tmp = path + ".tmp"
        with self.fs.open_output_stream(tmp) as stream:
            stream.write(data)
        self.fs.move(tmp, path)

    def list_files(self, directory: str, suffix: str) -> list[str]:
        """Every file under `directory` ending in `suffix`, sorted. Empty if it doesn't exist."""
        selector = pafs.FileSelector(directory, recursive=True, allow_not_found=True)
        infos = self.fs.get_file_info(selector)
        return sorted(
            i.path for i in infos if i.type == pafs.FileType.File and i.path.endswith(suffix)
        )

    def delete_dir(self, directory: str) -> None:
        if self.fs.get_file_info(directory).type != pafs.FileType.NotFound:
            self.fs.delete_dir(directory)


@cache
def store() -> Storage:
    """The storage root for this process, from F1_DATA_DIR."""
    return Storage(os.environ.get("F1_DATA_DIR", "data"))


def bronze_path(source: str, endpoint: str, **partitions: object) -> str:
    """Hive-style path, e.g. bronze/jolpica/results/season=2023/round=01.json."""
    parts = [f"{key}={value}" for key, value in partitions.items()]
    parts[-1] += ".json"
    return store().path("bronze", source, endpoint, *parts)


def write_bronze(path: str, payload: Any, source_url: str) -> None:
    """Write one raw API response with when and where it came from."""
    envelope = {
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_url": source_url,
        "payload": payload,
    }
    store().write_bytes(path, json.dumps(envelope, ensure_ascii=False).encode())


def _envelope(path: str) -> dict[str, Any]:
    return json.loads(store().read_bytes(path))


def read_bronze(path: str) -> Any:
    """Return the payload of a bronze file."""
    return _envelope(path)["payload"]


def is_final(path: str, settled_at: datetime) -> bool:
    """True when the file was fetched after the data settled, so it never needs refetching.

    Stewards can still change results for a few days after a race, which is why callers
    pass a `settled_at` some days after the session rather than the session time itself.
    """
    if not store().exists(path):
        return False
    return datetime.fromisoformat(_envelope(path)["fetched_at"]) >= settled_at
