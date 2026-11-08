{{ config(tags=["reconcile"]) }}
-- Reconciliation with a race whose facts are well known: 2023 Australian GP had three red flags,
-- Verstappen won, and Sainz got a 5-second penalty for causing a collision at the last restart.
with checks as (
    select 'red_flags' as fact, (
        select red_flags from {{ ref('mart_race_crashes') }}
        where season = 2023 and round = 3 and session_type = 'race'
    ) = 3 as ok
    union all
    select 'winner', (
        select driver_code from {{ ref('mart_race_winners') }}
        where season = 2023 and round = 3 and session_type = 'race'
    ) = 'VER'
    union all
    select 'sainz_penalty', (
        select count(*) from {{ ref('mart_penalties') }}
        where season = 2023 and round = 3 and driver_code = 'SAI'
            and penalty_seconds = 5 and reason = 'CAUSING A COLLISION'
    ) = 1
)

select fact from checks where not coalesce(ok, false)
