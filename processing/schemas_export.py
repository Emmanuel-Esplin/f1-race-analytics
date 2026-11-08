"""Write the silver schemas as JSON for Terraform, so Glue tables match the Parquet exactly.

Run `make schemas` after changing processing/silver.py; a test fails if the file is stale.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa

from processing.silver import SCHEMAS

TARGET = Path(__file__).resolve().parents[1] / "infra" / "silver_schemas.json"
GLUE_TYPES = {pa.string(): "string", pa.int64(): "bigint", pa.float64(): "double"}


def glue_schemas() -> dict[str, list[dict[str, str]]]:
    """Table to Glue columns. season is left out: it is the partition key."""
    return {
        table: [
            {"name": field.name, "type": GLUE_TYPES[field.type]}
            for field in schema
            if field.name != "season"
        ]
        for table, schema in SCHEMAS.items()
    }


def render() -> str:
    return json.dumps(glue_schemas(), indent=2) + "\n"


if __name__ == "__main__":
    TARGET.write_text(render())
