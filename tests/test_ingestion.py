from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from tenacity import wait_none

from ingestion import jolpica, landing, openf1
from ingestion.client import ApiClient, LiveSessionLockError
from ingestion.run import parse_seasons


@pytest.fixture(autouse=True)
def bronze_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(landing, "DATA_DIR", tmp_path)
    # No real back-off sleeps in tests.
    monkeypatch.setattr(ApiClient.get_json.retry, "wait", wait_none())
    return tmp_path


def client_for(handler) -> ApiClient:
    return ApiClient("https://example.test", 0, transport=httpx.MockTransport(handler))


def test_retries_transient_errors_then_succeeds():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json={"ok": 1})

    assert client_for(handler).get_json("/x") == {"ok": 1}
    assert len(calls) == 3


def test_live_session_lock_is_its_own_error_and_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, json={"detail": "Live F1 session in progress. ..."})

    with pytest.raises(LiveSessionLockError):
        client_for(handler).get_json("/sessions")
    assert len(calls) == 1


def test_client_errors_are_not_retried():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        client_for(handler).get_json("/missing")
    assert len(calls) == 1


def test_bronze_path_is_hive_style(bronze_dir):
    path = landing.bronze_path("jolpica", "results", season=2023, round="01")
    assert path == bronze_dir / "bronze/jolpica/results/season=2023/round=01.json"
    assert landing.bronze_path("openf1", "sessions", season=2024).name == "season=2024.json"


def test_is_final_compares_fetch_time_with_settle_time(bronze_dir):
    path = bronze_dir / "x.json"
    assert not landing.is_final(path, datetime.now(UTC))
    landing.write_bronze(path, [1], "https://example.test")
    assert landing.read_bronze(path) == [1]
    assert landing.is_final(path, datetime.now(UTC) - timedelta(days=1))
    assert not landing.is_final(path, datetime.now(UTC) + timedelta(days=1))


def mrdata(total: int, offset: int, **body) -> dict:
    return {"MRData": {"total": str(total), "limit": "100", "offset": str(offset), **body}}


def test_fetch_all_pages_follows_offsets():
    def handler(request):
        offset = int(request.url.params["offset"])
        return httpx.Response(200, json=mrdata(250, offset))

    pages = jolpica.fetch_all_pages(client_for(handler), "/2023/1/laps.json")
    assert [p["offset"] for p in pages] == ["0", "100", "200"]


def test_jolpica_season_skips_future_races_and_adds_sprints(bronze_dir):
    races = [
        {"round": "1", "date": "2026-03-08"},
        {"round": "2", "date": "2026-03-15", "Sprint": {"date": "2026-03-14"}},
        {"round": "3", "date": "2026-12-06"},
    ]
    requested = []

    def handler(request):
        requested.append(request.url.path)
        return httpx.Response(200, json=mrdata(1, 0, RaceTable={"Races": races}))

    written = jolpica.ingest_season(client_for(handler), 2026, date(2026, 11, 8))
    assert written == 1 + 4 + 5  # calendar, round 1, round 2 with sprint
    assert not any("/2026/3/" in path for path in requested)
    assert (bronze_dir / "bronze/jolpica/sprint/season=2026/round=02.json").exists()

    # A second run refetches only the calendar of the season still in progress.
    requested.clear()
    assert jolpica.ingest_season(client_for(handler), 2026, date(2026, 11, 8)) == 1


def test_openf1_lands_finished_race_sessions_only(bronze_dir):
    now = datetime(2026, 11, 8, 17, 0, tzinfo=UTC)
    sessions = [
        {"session_key": 1, "session_type": "Race", "date_end": "2026-11-01T22:00:00+00:00"},
        {"session_key": 2, "session_type": "Qualifying", "date_end": "2026-11-07T20:00:00+00:00"},
        {"session_key": 3, "session_type": "Race", "date_end": "2026-11-08T19:00:00+00:00"},
    ]

    def handler(request):
        if request.url.path == "/sessions":
            return httpx.Response(200, json=sessions)
        return httpx.Response(200, json=[{"session_key": request.url.params["session_key"]}])

    assert openf1.ingest_season(client_for(handler), 2026, now) == 3
    landed = sorted(p.name for p in (bronze_dir / "bronze/openf1/race_control").rglob("*.json"))
    assert landed == ["session_key=1.json"]


def test_parse_seasons():
    assert parse_seasons("2023-2025") == [2023, 2024, 2025]
    assert parse_seasons("2023,2026") == [2023, 2026]
