"""Jolpica (Ergast successor): calendar, results, sprints, lap positions and standings."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from ingestion.client import ApiClient
from ingestion.landing import bronze_path, is_final, read_bronze, write_bronze

BASE_URL = "https://api.jolpi.ca/ergast/f1"
PAGE_SIZE = 100  # The API's maximum.
# About 500 requests an hour are allowed, so stay just under that.
MIN_INTERVAL_S = 7.5
SETTLE_DAYS = 3

log = logging.getLogger(__name__)


def fetch_all_pages(client: ApiClient, path: str) -> list[dict[str, Any]]:
    """Return every MRData page of a paginated endpoint, raw."""
    pages: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = client.get_json(path, params={"limit": PAGE_SIZE, "offset": offset})["MRData"]
        pages.append(page)
        offset += PAGE_SIZE
        if offset >= int(page["total"]):
            return pages


def round_endpoints(race: dict[str, Any]) -> list[str]:
    """Endpoints to land for one round; sprints only exist on sprint weekends."""
    endpoints = ["results", "laps", "driverStandings", "constructorStandings"]
    if "Sprint" in race:
        endpoints.append("sprint")
    return endpoints


def settled_at(race: dict[str, Any]) -> datetime:
    """When a round's data stops changing."""
    race_day = date.fromisoformat(race["date"])
    return datetime.combine(race_day + timedelta(days=SETTLE_DAYS), time(), tzinfo=UTC)


def ingest_season(client: ApiClient, season: int, today: date, refresh: bool = False) -> int:
    """Land the calendar and every finished round of `season`. Returns files written."""
    written = 0
    calendar_file = bronze_path("jolpica", "races", season=season)
    season_over = date(season, 12, 31) + timedelta(days=SETTLE_DAYS) < today
    if refresh or not calendar_file.exists() or not season_over:
        pages = fetch_all_pages(client, f"/{season}.json")
        write_bronze(calendar_file, pages, f"{BASE_URL}/{season}.json")
        written += 1
    races = [race for page in read_bronze(calendar_file) for race in page["RaceTable"]["Races"]]

    for race in races:
        # A race on today's date may still be running.
        if date.fromisoformat(race["date"]) >= today:
            continue
        rnd = int(race["round"])
        for endpoint in round_endpoints(race):
            target = bronze_path("jolpica", endpoint, season=season, round=f"{rnd:02d}")
            if not refresh and is_final(target, settled_at(race)):
                continue
            path = f"/{season}/{rnd}/{endpoint}.json"
            log.info("jolpica %s", path)
            write_bronze(target, fetch_all_pages(client, path), BASE_URL + path)
            written += 1
    return written
