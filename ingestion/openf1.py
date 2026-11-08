"""OpenF1: race and sprint sessions, race-control messages and the driver list per session."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from ingestion.client import ApiClient
from ingestion.landing import bronze_path, is_final, read_bronze, store, write_bronze

BASE_URL = "https://api.openf1.org/v1"
# The free tier allows a few requests a second; one every two seconds is plenty.
MIN_INTERVAL_S = 2.0
SETTLE_DAYS = 3
SESSION_ENDPOINTS = ("race_control", "drivers")

log = logging.getLogger(__name__)


def race_sessions(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Grands prix and sprints only; practice and qualifying don't feed any mart."""
    return [s for s in sessions if s.get("session_type") == "Race"]


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def ingest_season(client: ApiClient, season: int, now: datetime, refresh: bool = False) -> int:
    """Land the session list and race-control data for every finished race session."""
    written = 0
    sessions_file = bronze_path("openf1", "sessions", season=season)
    season_over = datetime(season + 1, 1, 1, tzinfo=UTC) + timedelta(days=SETTLE_DAYS) < now
    if refresh or not store().exists(sessions_file) or not season_over:
        sessions = client.get_json("/sessions", params={"year": season})
        write_bronze(sessions_file, sessions, f"{BASE_URL}/sessions?year={season}")
        written += 1

    for session in race_sessions(read_bronze(sessions_file)):
        ended = _parse_time(session["date_end"])
        if ended >= now:
            continue
        key = session["session_key"]
        for endpoint in SESSION_ENDPOINTS:
            target = bronze_path("openf1", endpoint, season=season, session_key=key)
            if not refresh and is_final(target, ended + timedelta(days=SETTLE_DAYS)):
                continue
            log.info("openf1 %s session_key=%s", endpoint, key)
            rows = client.get_json(f"/{endpoint}", params={"session_key": key})
            write_bronze(target, rows, f"{BASE_URL}/{endpoint}?session_key={key}")
            written += 1
    return written
