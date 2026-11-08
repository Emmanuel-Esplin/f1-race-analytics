# Metric definitions

Seasons 2023 onward, because OpenF1 race-control data starts there.

| Question | Mart | Source |
| --- | --- | --- |
| Who won each race and sprint | `mart_race_winners` | Jolpica results, sprint |
| Crashes per race | `mart_race_crashes` | OpenF1 race control |
| Time lost to crashes | `mart_neutralised_time` | OpenF1 race control |
| Who led each race, lap by lap | `mart_lap_leaders` | Jolpica laps |
| Who leads the championship | `mart_championship_progression` | Jolpica standings |
| Penalties per driver | `mart_driver_penalties` | OpenF1 race control |

## Crashes

Jolpica stopped recording why a car retired after 2023: every retirement is just `Retired`.
So a crash comes from race control: an incident noted as a collision or crash, or a stopped car
that brought out a Safety Car, Virtual Safety Car or red flag. One event can involve several
cars; it counts once.

## Time lost to crashes

Minutes the race was neutralised: from `SAFETY CAR DEPLOYED` to `SAFETY CAR IN THIS LAP`, from
`VIRTUAL SAFETY CAR DEPLOYED` to `VSC ENDING`, and from `RED FLAG` to the restart. A period counts
as crash time when a crash was reported in the two laps before it started. Other periods (debris,
weather) are kept but labelled `other`.

## Penalties

Parsed from `FIA STEWARDS: ... PENALTY FOR CAR n (ABC)` messages in races and sprints. Penalties
decided after the session, such as grid drops for the next race, may only appear in FIA
documents and are then not counted.

## Data freshness

A round is refetched on each run until three days after the race, because stewards can still
change results. After that its bronze file is final.

OpenF1 refuses every unauthenticated request, past sessions included, while a live F1 session is
running. Ingestion then exits with code 75 and writes nothing; run it again after the session.
