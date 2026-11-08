"""End to end on a made-up race: bronze -> silver -> every dbt model and test on DuckDB.

The race is invented, so CI needs no API access and the repo holds no third-party data.
"""

import os
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from ingestion import landing
from processing import silver

DBT = Path(sys.executable).parent / "dbt"
PROJECT = Path(__file__).resolve().parents[1] / "transform"

DRIVERS = [
    ("alpha", "ALP", 1, "Ann", "Alpha", "red", "Red Team"),
    ("bravo", "BRA", 2, "Bob", "Bravo", "blue", "Blue Team"),
    ("charlie", "CHA", 3, "Cat", "Charlie", "blue", "Blue Team"),
]


def driver(d):
    return {"driverId": d[0], "code": d[1], "givenName": d[3], "familyName": d[4]}


def result(d, position, laps, status, millis=None):
    row = {
        "number": str(d[2]),
        "position": str(position) if position else "R",
        "positionText": str(position) if position else "R",
        "points": "25" if position == 1 else "0",
        "grid": str(d[2]),
        "laps": str(laps),
        "status": status,
        "Driver": driver(d),
        "Constructor": {"constructorId": d[5], "name": d[6]},
    }
    if millis:
        row["Time"] = {"millis": str(millis), "time": "1:00:00.000"}
    return row


def race_page(**body):
    return {"total": "1", "RaceTable": {"Races": [{"season": "2023", "round": "1", **body}]}}


def standings(key, rows):
    lists = [{"season": "2023", "round": "1", key: rows}]
    return [{"total": "1", "StandingsTable": {"StandingsLists": lists}}]


def rc(time, lap, message, category="Other"):
    return {
        "session_key": 100,
        "date": f"2023-03-05T15:{time}+00:00",
        "lap_number": lap,
        "category": category,
        "message": message,
    }


def land(endpoint, payload, **partitions):
    source = "openf1" if endpoint in ("sessions", "race_control", "drivers") else "jolpica"
    path = landing.bronze_path(source, endpoint, season=2023, **partitions)
    landing.write_bronze(path, payload, "https://example.test")


@pytest.fixture
def warehouse(bronze_dir):
    alp, bra, cha = DRIVERS
    circuit = {
        "circuitId": "test",
        "circuitName": "Test Ring",
        "Location": {"locality": "Testville", "country": "Testland"},
    }
    land("races", [race_page(raceName="Test Grand Prix", date="2023-03-05", Circuit=circuit)])
    results = [
        result(alp, 1, 3, "Finished", 3_600_000),
        result(bra, 2, 3, "Finished", 3_605_000),
        result(cha, None, 1, "Retired"),
    ]
    land("results", [race_page(Results=results)], round="01")
    laps = [
        {
            "number": "1",
            "Timings": [
                {"driverId": "bravo", "position": "1", "time": "1:30.000"},
                {"driverId": "alpha", "position": "2", "time": "1:30.500"},
            ],
        },
        {"number": "2", "Timings": [{"driverId": "alpha", "position": "1", "time": "1:31.000"}]},
        {"number": "3", "Timings": [{"driverId": "alpha", "position": "1", "time": "1:31.000"}]},
    ]
    land("laps", [race_page(Laps=laps)], round="01")
    land(
        "driverStandings",
        standings(
            "DriverStandings",
            [
                {
                    "position": "1",
                    "points": "25",
                    "wins": "1",
                    "Driver": driver(alp),
                    "Constructors": [{"constructorId": "red"}],
                },
                {
                    "position": "2",
                    "points": "18",
                    "wins": "0",
                    "Driver": driver(bra),
                    "Constructors": [{"constructorId": "blue"}],
                },
            ],
        ),
        round="01",
    )
    land(
        "constructorStandings",
        standings(
            "ConstructorStandings",
            [
                {
                    "position": "1",
                    "points": "25",
                    "wins": "1",
                    "Constructor": {"constructorId": "red", "name": "Red Team"},
                },
                {
                    "position": "2",
                    "points": "18",
                    "wins": "0",
                    "Constructor": {"constructorId": "blue", "name": "Blue Team"},
                },
            ],
        ),
        round="01",
    )
    land(
        "sessions",
        [
            {
                "year": 2023,
                "session_key": 100,
                "meeting_key": 1,
                "session_type": "Race",
                "session_name": "Race",
                "date_start": "2023-03-05T15:00:00+00:00",
                "date_end": "2023-03-05T17:00:00+00:00",
            }
        ],
    )
    land(
        "race_control",
        [
            rc("00:00", 1, "SESSION STARTED", "SessionStatus"),
            rc("02:00", 1, "CAR 3 (CHA) STOPPED AT TURN 4", "CarEvent"),
            rc("02:30", 2, "SAFETY CAR DEPLOYED", "SafetyCar"),
            rc(
                "03:00",
                2,
                "TURN 1 INCIDENT INVOLVING CARS 1 (ALP) AND 2 (BRA) NOTED - CAUSING A COLLISION",
            ),
            rc(
                "04:00",
                2,
                "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 2 (BRA)"
                " - CAUSING A COLLISION (15:03:00)",
            ),
            rc(
                "05:00",
                2,
                "FIA STEWARDS: PENALTY SERVED - 5 SECOND TIME PENALTY FOR CAR 2 (BRA)"
                " - CAUSING A COLLISION",
            ),
            rc("06:30", 3, "TRACK CLEAR", "Flag"),
            rc("10:00", 3, "SESSION FINISHED", "SessionStatus"),
            rc("11:00", 3, "RED FLAG", "Flag"),  # after the finish: must be ignored
        ],
        session_key=100,
    )
    land(
        "drivers",
        [{"session_key": 100, "driver_number": d[2], "name_acronym": d[1]} for d in DRIVERS],
        session_key=100,
    )

    for table in silver.TABLES:
        silver.build_table(table, landing.store())
    (bronze_dir / "gold").mkdir()
    env = {
        **os.environ,
        "F1_DATA_DIR": str(bronze_dir),
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
        "DBT_TARGET_PATH": str(bronze_dir / "target"),
        "DBT_LOG_PATH": str(bronze_dir / "logs"),
    }
    run = subprocess.run(
        [str(DBT), "build", "--profiles-dir", ".", "--exclude", "tag:reconcile"],
        cwd=PROJECT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert run.returncode == 0, run.stdout[-3000:]
    con = duckdb.connect(str(bronze_dir / "gold" / "warehouse.duckdb"), read_only=True)
    yield con
    con.close()


def one(con, sql):
    return con.sql(sql).fetchone()


def test_marts_answer_the_five_questions(warehouse):
    assert one(warehouse, "select driver_code, margin_to_second_ms from mart_race_winners") == (
        "ALP",
        5000,
    )
    # Safety Car from 15:02:30 to TRACK CLEAR at 15:06:30; the red flag after the finish is ignored.
    assert one(
        warehouse, "select count(*), sum(duration_min), min(cause) from mart_neutralised_time"
    ) == (1, 4.0, "collision")
    # One collision (ALP/BRA) plus the stopped car CHA.
    assert one(
        warehouse,
        "select crashes, collisions, stopped_cars, time_lost_to_crashes_min from mart_race_crashes",
    ) == (2, 1, 1, 4.0)
    assert warehouse.sql(
        "select driver_code, laps_led, race_lead_changes from mart_lap_leaders order by driver_code"
    ).fetchall() == [("ALP", 2, 1), ("BRA", 1, 1)]
    # The PENALTY SERVED line repeats the penalty and must not count twice.
    assert one(
        warehouse,
        "select driver_code, penalties, penalty_seconds, for_collisions from mart_driver_penalties",
    ) == ("BRA", 1, 5, 1)
