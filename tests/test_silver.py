import pyarrow.parquet as pq

from ingestion import landing
from processing import silver

DRIVER = {
    "driverId": "max_verstappen",
    "code": "VER",
    "givenName": "Max",
    "familyName": "Verstappen",
}
TEAM = {"constructorId": "red_bull", "name": "Red Bull"}


def race(**extra) -> dict:
    return {"season": "2023", "round": "4", **extra}


def test_lap_time_ms():
    assert silver.lap_time_ms("1:39.019") == 99019
    assert silver.lap_time_ms("59.5") == 59500
    assert silver.lap_time_ms(None) is None


def test_results_rows_types_non_finishers_as_null_position():
    result = {
        "number": "1",
        "position": "R",
        "positionText": "R",
        "points": "0",
        "grid": "1",
        "laps": "10",
        "status": "Retired",
        "Driver": DRIVER,
        "Constructor": TEAM,
    }
    pages = [{"RaceTable": {"Races": [race(SprintResults=[result])]}}]
    [row] = silver.results_rows(pages, "sprint")
    assert row["session_type"] == "sprint"
    assert row["position"] is None and row["position_text"] == "R"
    assert row["driver_name"] == "Max Verstappen" and row["time_millis"] is None


def test_lap_positions_concatenate_a_lap_split_across_pages():
    def page(*timings):
        return {"RaceTable": {"Races": [race(Laps=[{"number": "16", "Timings": list(timings)}])]}}

    pages = [
        page({"driverId": "a", "position": "1", "time": "1:40.000"}),
        page({"driverId": "b", "position": "2", "time": "1:40.500"}),
    ]
    rows = list(silver.lap_position_rows(pages))
    assert [(r["lap"], r["driver_id"], r["position"]) for r in rows] == [(16, "a", 1), (16, "b", 2)]


def test_driver_standings_take_latest_team():
    standing = {
        "position": "1",
        "points": "25",
        "wins": "1",
        "Driver": DRIVER,
        "Constructors": [{"constructorId": "alphatauri"}, {"constructorId": "red_bull"}],
    }
    pages = [{"StandingsTable": {"StandingsLists": [race(DriverStandings=[standing])]}}]
    [row] = silver.driver_standing_rows(pages)
    assert row["constructor_id"] == "red_bull" and row["points"] == 25.0


def test_session_rows_keep_races_and_sprints_only():
    sessions = [
        {
            "year": 2023,
            "session_key": 1,
            "session_type": "Race",
            "session_name": "Sprint",
            "date_start": "a",
            "date_end": "b",
        },
        {
            "year": 2023,
            "session_key": 2,
            "session_type": "Practice",
            "session_name": "Practice 1",
            "date_start": "a",
            "date_end": "b",
        },
    ]
    assert [r["session_key"] for r in silver.session_rows(sessions)] == [1]


def test_build_table_writes_one_parquet_per_season(tmp_path, monkeypatch):
    monkeypatch.setattr(landing, "DATA_DIR", tmp_path)
    for season in (2023, 2024):
        messages = [
            {
                "session_key": 9,
                "date": "2023-03-05T15:10:00+00:00",
                "lap_number": 3,
                "category": "SafetyCar",
                "message": "SAFETY CAR DEPLOYED",
            }
        ]
        path = landing.bronze_path("openf1", "race_control", season=season, session_key=9)
        landing.write_bronze(path, messages, "https://example.test")

    assert silver.build_table("race_control", tmp_path) == 2
    table = pq.read_table(tmp_path / "silver/race_control/season=2024/part-0.parquet")
    assert table.column("season").to_pylist() == [2024]
    assert table.schema == silver.SCHEMAS["race_control"]
