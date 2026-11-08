"""Lambda entry points for the three pipeline steps Step Functions runs in order.

All three share one container image. F1_DATA_DIR is s3://<bucket>, so bronze and silver
are read and written straight in S3.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ingestion.run import ingest

logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger(__name__)

DBT_PROJECT = Path(os.environ.get("LAMBDA_TASK_ROOT", ".")) / "transform"


def ingest_handler(event: dict[str, Any], _context: object) -> dict[str, Any]:
    """Fetch new data. Defaults to the current season; finished rounds are skipped.

    LiveSessionLockError is left to propagate: Step Functions retries it an hour later.
    """
    seasons = event.get("seasons") or [datetime.now(UTC).year]
    sources = event.get("sources") or ["jolpica", "openf1"]
    written = ingest(sources, [int(s) for s in seasons], bool(event.get("refresh")))
    log.info("wrote %d bronze files", written)
    return {"written": written}


def silver_handler(_event: dict[str, Any], _context: object) -> dict[str, Any]:
    """Rebuild every silver table from bronze."""
    from ingestion.landing import store
    from processing.silver import TABLES, build_table

    return {table: build_table(table, store()) for table in TABLES}


def dbt_handler(event: dict[str, Any], _context: object) -> dict[str, Any]:
    """Build and test the marts on Athena."""
    from dbt.cli.main import dbtRunner

    # The image is read-only outside /tmp.
    os.environ.setdefault("DBT_TARGET_PATH", "/tmp/dbt/target")
    os.environ.setdefault("DBT_LOG_PATH", "/tmp/dbt/logs")
    os.environ["DBT_SEND_ANONYMOUS_USAGE_STATS"] = "false"
    args = [
        event.get("command", "build"),
        "--project-dir",
        str(DBT_PROJECT),
        "--profiles-dir",
        str(DBT_PROJECT),
        "--target",
        "athena",
    ]
    result = dbtRunner().invoke(args)
    if not result.success:
        raise RuntimeError(f"dbt {args[0]} failed: {result.exception or 'see the log'}")
    return {"dbt": args[0], "success": True}
