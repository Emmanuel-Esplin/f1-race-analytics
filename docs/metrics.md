# Metric definitions

Seasons 2023 onward, because OpenF1 race-control data starts there. Every mart covers races and
sprints (`session_type`). A round appears once Jolpica has results for it, the day after the race.

| Question | Mart | Source |
| --- | --- | --- |
| Who won each race and sprint | `mart_race_winners` | Jolpica results, sprint |
| Crashes per race | `mart_race_crashes` | OpenF1 race control, Jolpica results |
| Time lost to crashes | `mart_neutralised_time`, `mart_race_crashes` | OpenF1 race control |
| Who led each race, lap by lap | `mart_lap_leaders` | Jolpica laps |
| Who leads the championship | `mart_championship_progression` | Jolpica standings |
| Penalties per driver | `mart_driver_penalties`, `mart_penalties` | OpenF1 race control |

## Neutralised periods

Built from race-control messages in `int_neutralised_periods`:

| Period | Starts at | Ends at |
| --- | --- | --- |
| Safety Car | `SAFETY CAR DEPLOYED` | next `TRACK CLEAR` (the green flag), or a red flag |
| Virtual Safety Car | `VIRTUAL SAFETY CAR DEPLOYED`, or `VSC DEPLOYED` from 2026 | next `TRACK CLEAR`, or a red flag |
| Red flag | `RED FLAG` or `SESSION ABORTED` (the feed has used both) | `SESSION STARTED` (the restart) |

Messages after `SESSION FINISHED` are ignored: race control sometimes shows a red flag after the
chequered flag to stop cars on track. A Safety Car that turns into a red flag is two periods.

## Crashes

Jolpica does not say why a car retired: nearly every retirement since 2023 is just `Retired`. So
a crash is either:

- **a collision**: race control's `INCIDENT INVOLVING CARS ... NOTED - CAUSING A COLLISION`.
  The stewards' follow-ups about the same incident are not counted again; or
- **a stopped car**: a car that retired from two laps before to one lap after the start of a
  Safety Car, VSC or red flag, and was not part of a collision then. Counted once per car.

Limitation: race control doesn't say why a car stopped, so a breakdown that brings out a Safety
Car counts as a crash. A single-car spin that causes no neutralisation and no retirement is not
seen at all.

## Time lost to crashes

`time_lost_to_crashes_min` is the minutes of Safety Car, VSC and red flag whose cause is a crash:
a collision or a stopped car in that same window. Other periods (debris, weather, a pre-start
rain delay) are kept in `mart_neutralised_time` with `cause = 'other'`.

## Penalties

Parsed from `FIA STEWARDS: <n> SECOND TIME | DRIVE THROUGH | STOP-AND-GO | <n> SECOND STOP/GO
PENALTY FOR CAR <n> (<ABC>) - <reason>`. `PENALTY SERVED` lines repeat an earlier penalty and are
not counted. Penalties decided after the session, such as grid drops for the next race, may only
appear in FIA documents and are then not counted. No penalty in the 2023 to 2026 data was
rescinded in race control.

## Data freshness

A round is refetched on each run until three days after the race, because stewards can still
change results. After that its bronze file is final.

OpenF1 refuses every unauthenticated request, past sessions included, while a live F1 session is
running. Ingestion then exits with code 75 (Step Functions retries hourly) and writes nothing.
Cancelled races (2023 Imola) are skipped.

## Checks

- dbt tests: unique keys, accepted values, one leader per lap and per round, every neutralised
  period ends after it starts.
- `assert_known_2023_australia` (tag `reconcile`): three red flags, Verstappen won, Sainz's
  5-second penalty. Runs on real data only.
- `tests/test_dbt_pipeline.py` builds a made-up race end to end, so CI tests the parsing rules
  without any API or third-party data.
