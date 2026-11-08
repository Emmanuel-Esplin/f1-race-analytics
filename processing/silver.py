"""Bronze JSON to typed silver Parquet, one file per table and season.

Flattening happens here rather than in dbt so the same SQL runs on DuckDB and Athena:
Athena reads nested JSON poorly, and both engines read flat Parquet the same way.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable, Iterator
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from ingestion import landing

Row = dict[str, Any]

log = logging.getLogger(__name__)


def _int(value: Any) -> int | None:
    # Jolpica sends every number as a string, and positions as "R", "D" etc. for non-finishers.
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def lap_time_ms(text: str | None) -> int | None:
    """'1:39.019' to 99019."""
    if not text:
        return None
    minutes, _, seconds = text.rpartition(":")
    return round((int(minutes or 0) * 60 + float(seconds)) * 1000)


def _races(pages: list[Row]) -> Iterator[Row]:
    for page in pages:
        yield from page["RaceTable"]["Races"]


# --- Jolpica ------------------------------------------------------------------------------


def races_rows(pages: list[Row]) -> Iterator[Row]:
    """One row per round of the calendar."""
    for race in _races(pages):
        circuit = race["Circuit"]
        sprint = race.get("Sprint") or {}
        yield {
            "season": int(race["season"]),
            "round": int(race["round"]),
            "race_name": race["raceName"],
            "circuit_id": circuit["circuitId"],
            "circuit_name": circuit["circuitName"],
            "locality": circuit["Location"]["locality"],
            "country": circuit["Location"]["country"],
            "race_date": race["date"],
            "race_time": race.get("time"),
            "sprint_date": sprint.get("date"),
        }


def results_rows(pages: list[Row], session_type: str) -> Iterator[Row]:
    """One row per driver per race or sprint."""
    key = "Results" if session_type == "race" else "SprintResults"
    for race in _races(pages):
        for result in race.get(key, []):
            driver, constructor = result["Driver"], result["Constructor"]
            yield {
                "season": int(race["season"]),
                "round": int(race["round"]),
                "session_type": session_type,
                "driver_id": driver["driverId"],
                "driver_code": driver.get("code"),
                "driver_number": _int(result.get("number")),
                "driver_name": f"{driver['givenName']} {driver['familyName']}",
                "constructor_id": constructor["constructorId"],
                "constructor_name": constructor["name"],
                "grid": _int(result.get("grid")),
                "position": _int(result.get("position")),
                "position_text": result.get("positionText"),
                "points": _float(result.get("points")),
                "laps": _int(result.get("laps")),
                "status": result.get("status"),
                "time_millis": _int((result.get("Time") or {}).get("millis")),
                "gap_text": (result.get("Time") or {}).get("time"),
            }


def lap_position_rows(pages: list[Row]) -> Iterator[Row]:
    """One row per driver per lap. A lap can span two pages, so pages are simply concatenated."""
    for race in _races(pages):
        for lap in race.get("Laps", []):
            for timing in lap["Timings"]:
                yield {
                    "season": int(race["season"]),
                    "round": int(race["round"]),
                    "lap": int(lap["number"]),
                    "driver_id": timing["driverId"],
                    "position": _int(timing.get("position")),
                    "lap_time_ms": lap_time_ms(timing.get("time")),
                }


def _standings_lists(pages: list[Row]) -> Iterator[Row]:
    for page in pages:
        yield from page["StandingsTable"]["StandingsLists"]


def driver_standing_rows(pages: list[Row]) -> Iterator[Row]:
    """Championship table after one round."""
    for table in _standings_lists(pages):
        for row in table["DriverStandings"]:
            driver = row["Driver"]
            # A driver who changed team mid-season lists every team; the latest is last.
            team = row["Constructors"][-1] if row.get("Constructors") else {}
            yield {
                "season": int(table["season"]),
                "round": int(table["round"]),
                "driver_id": driver["driverId"],
                "driver_code": driver.get("code"),
                "driver_name": f"{driver['givenName']} {driver['familyName']}",
                "constructor_id": team.get("constructorId"),
                "position": _int(row.get("position")),
                "points": _float(row.get("points")),
                "wins": _int(row.get("wins")),
            }


def constructor_standing_rows(pages: list[Row]) -> Iterator[Row]:
    """Constructors' table after one round."""
    for table in _standings_lists(pages):
        for row in table["ConstructorStandings"]:
            yield {
                "season": int(table["season"]),
                "round": int(table["round"]),
                "constructor_id": row["Constructor"]["constructorId"],
                "constructor_name": row["Constructor"]["name"],
                "position": _int(row.get("position")),
                "points": _float(row.get("points")),
                "wins": _int(row.get("wins")),
            }


# --- OpenF1 -------------------------------------------------------------------------------


def session_rows(sessions: list[Row]) -> Iterator[Row]:
    """Race and sprint sessions; their date links them to Jolpica rounds."""
    for s in sessions:
        # Cancelled races (2023 Imola) are listed but never ran.
        if s.get("session_type") != "Race" or s.get("is_cancelled"):
            continue
        yield {
            "season": int(s["year"]),
            "session_key": int(s["session_key"]),
            "meeting_key": _int(s.get("meeting_key")),
            "session_name": s["session_name"],
            "date_start": s["date_start"],
            "date_end": s["date_end"],
            "country_name": s.get("country_name"),
            "location": s.get("location"),
            "circuit_short_name": s.get("circuit_short_name"),
        }


def race_control_rows(messages: list[Row], season: int) -> Iterator[Row]:
    """Every race-control message: flags, Safety Car, incidents and stewards' decisions."""
    for m in messages:
        yield {
            "season": season,
            "session_key": int(m["session_key"]),
            "message_at": m["date"],
            "lap_number": _int(m.get("lap_number")),
            "category": m.get("category"),
            "flag": m.get("flag"),
            "scope": m.get("scope"),
            "sector": _int(m.get("sector")),
            "driver_number": _int(m.get("driver_number")),
            "message": m.get("message"),
        }


def driver_rows(drivers: list[Row], season: int) -> Iterator[Row]:
    """Car number to driver for one session; numbers are only unique within a session."""
    for d in drivers:
        yield {
            "season": season,
            "session_key": int(d["session_key"]),
            "driver_number": int(d["driver_number"]),
            "name_acronym": d.get("name_acronym"),
            "full_name": d.get("full_name"),
            "team_name": d.get("team_name"),
        }


# --- Writing ------------------------------------------------------------------------------

STRING, INT, FLOAT = pa.string(), pa.int64(), pa.float64()

SCHEMAS: dict[str, pa.Schema] = {
    "races": pa.schema(
        [
            ("season", INT),
            ("round", INT),
            ("race_name", STRING),
            ("circuit_id", STRING),
            ("circuit_name", STRING),
            ("locality", STRING),
            ("country", STRING),
            ("race_date", STRING),
            ("race_time", STRING),
            ("sprint_date", STRING),
        ]
    ),
    "results": pa.schema(
        [
            ("season", INT),
            ("round", INT),
            ("session_type", STRING),
            ("driver_id", STRING),
            ("driver_code", STRING),
            ("driver_number", INT),
            ("driver_name", STRING),
            ("constructor_id", STRING),
            ("constructor_name", STRING),
            ("grid", INT),
            ("position", INT),
            ("position_text", STRING),
            ("points", FLOAT),
            ("laps", INT),
            ("status", STRING),
            ("time_millis", INT),
            ("gap_text", STRING),
        ]
    ),
    "lap_positions": pa.schema(
        [
            ("season", INT),
            ("round", INT),
            ("lap", INT),
            ("driver_id", STRING),
            ("position", INT),
            ("lap_time_ms", INT),
        ]
    ),
    "driver_standings": pa.schema(
        [
            ("season", INT),
            ("round", INT),
            ("driver_id", STRING),
            ("driver_code", STRING),
            ("driver_name", STRING),
            ("constructor_id", STRING),
            ("position", INT),
            ("points", FLOAT),
            ("wins", INT),
        ]
    ),
    "constructor_standings": pa.schema(
        [
            ("season", INT),
            ("round", INT),
            ("constructor_id", STRING),
            ("constructor_name", STRING),
            ("position", INT),
            ("points", FLOAT),
            ("wins", INT),
        ]
    ),
    "sessions": pa.schema(
        [
            ("season", INT),
            ("session_key", INT),
            ("meeting_key", INT),
            ("session_name", STRING),
            ("date_start", STRING),
            ("date_end", STRING),
            ("country_name", STRING),
            ("location", STRING),
            ("circuit_short_name", STRING),
        ]
    ),
    "race_control": pa.schema(
        [
            ("season", INT),
            ("session_key", INT),
            ("message_at", STRING),
            ("lap_number", INT),
            ("category", STRING),
            ("flag", STRING),
            ("scope", STRING),
            ("sector", INT),
            ("driver_number", INT),
            ("message", STRING),
        ]
    ),
    "drivers": pa.schema(
        [
            ("season", INT),
            ("session_key", INT),
            ("driver_number", INT),
            ("name_acronym", STRING),
            ("full_name", STRING),
            ("team_name", STRING),
        ]
    ),
}

# Silver table -> (bronze source/endpoint, row builder taking (payload, season)).
Builder = Callable[[Any, int], Iterator[Row]]
TABLES: dict[str, list[tuple[str, Builder]]] = {
    "races": [("jolpica/races", lambda p, s: races_rows(p))],
    "results": [
        ("jolpica/results", lambda p, s: results_rows(p, "race")),
        ("jolpica/sprint", lambda p, s: results_rows(p, "sprint")),
    ],
    "lap_positions": [("jolpica/laps", lambda p, s: lap_position_rows(p))],
    "driver_standings": [("jolpica/driverStandings", lambda p, s: driver_standing_rows(p))],
    "constructor_standings": [
        ("jolpica/constructorStandings", lambda p, s: constructor_standing_rows(p))
    ],
    "sessions": [("openf1/sessions", lambda p, s: session_rows(p))],
    "race_control": [("openf1/race_control", race_control_rows)],
    "drivers": [("openf1/drivers", driver_rows)],
}


def _bronze_files(store: landing.Storage, endpoint: str) -> Iterator[tuple[int, str]]:
    # Files sit at season=YYYY.json or season=YYYY/<key>.json.
    for path in store.list_files(store.path("bronze", endpoint), ".json"):
        season_part = next(p for p in path.split("/") if p.startswith("season="))
        yield int(season_part.removesuffix(".json").split("=")[1]), path


def build_table(table: str, store: landing.Storage) -> int:
    """Rebuild one silver table from all of bronze. Returns the row count."""
    rows_by_season: dict[int, list[Row]] = {}
    for endpoint, build in TABLES[table]:
        for season, path in _bronze_files(store, endpoint):
            rows_by_season.setdefault(season, []).extend(build(landing.read_bronze(path), season))

    # Rebuilt from scratch, so a season removed from bronze can't linger in silver.
    store.delete_dir(store.path("silver", table))
    total = 0
    for season, rows in sorted(rows_by_season.items()):
        target = store.path("silver", table, f"season={season}", "part-0.parquet")
        store.make_parent(target)
        table_data = pa.Table.from_pylist(rows, schema=SCHEMAS[table])
        pq.write_table(table_data, target, filesystem=store.fs)
        total += len(rows)
    return total


def main(argv: list[str] | None = None) -> int:
    """Rebuild every silver table (or the ones named) from bronze."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tables", nargs="*", help=f"default: all of {', '.join(TABLES)}")
    args = parser.parse_args(argv)
    unknown = set(args.tables) - set(TABLES)
    if unknown:
        parser.error(f"unknown tables: {', '.join(sorted(unknown))}")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for table in args.tables or TABLES:
        log.info("silver %s: %d rows", table, build_table(table, landing.store()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
