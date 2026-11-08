"""Command line entry point: `python -m ingestion.run --source jolpica --seasons 2023-2026`."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime

from ingestion import jolpica, openf1
from ingestion.client import ApiClient, LiveSessionLockError, OutOfTimeError

FIRST_SEASON = 2023  # OpenF1 race-control data starts here.


def parse_seasons(text: str) -> list[int]:
    """'2023-2026' or '2024' or '2023,2025' to a list of seasons."""
    seasons: list[int] = []
    for part in text.split(","):
        start, _, end = part.partition("-")
        seasons.extend(range(int(start), int(end or start) + 1))
    if min(seasons) < FIRST_SEASON:
        raise argparse.ArgumentTypeError(f"seasons start at {FIRST_SEASON}")
    return seasons


def ingest(
    sources: list[str], seasons: list[int], refresh: bool = False, deadline: float | None = None
) -> dict[str, int | bool]:
    """Land bronze files for `sources` and `seasons`.

    Stops early once `deadline` (a time.monotonic() value) passes, returning complete=False;
    a rerun carries on, because finished files are skipped. Raises LiveSessionLockError if
    OpenF1 is locked.
    """
    now = datetime.now(UTC)
    written = 0
    try:
        if "jolpica" in sources:
            with ApiClient(jolpica.BASE_URL, jolpica.MIN_INTERVAL_S, deadline=deadline) as client:
                for season in seasons:
                    written += jolpica.ingest_season(client, season, now.date(), refresh)
        if "openf1" in sources:
            with ApiClient(openf1.BASE_URL, openf1.MIN_INTERVAL_S, deadline=deadline) as client:
                for season in seasons:
                    written += openf1.ingest_season(client, season, now, refresh)
    except OutOfTimeError:
        return {"written": written, "complete": False}
    return {"written": written, "complete": True}


def main(argv: list[str] | None = None) -> int:
    """Land bronze files for the chosen source and seasons."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["jolpica", "openf1", "all"], default="all")
    default_seasons = f"{FIRST_SEASON}-{datetime.now(UTC).year}"
    parser.add_argument("--seasons", type=parse_seasons, default=default_seasons)
    parser.add_argument("--refresh", action="store_true", help="refetch files already final")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    sources = ["jolpica", "openf1"] if args.source == "all" else [args.source]
    try:
        result = ingest(sources, args.seasons, args.refresh)
    except LiveSessionLockError:
        # Exit 75 (EX_TEMPFAIL) so a scheduler knows to retry, not to alert.
        logging.warning("OpenF1 is locked during a live session; try again after it ends")
        return 75
    logging.info("wrote %d bronze files", result["written"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
