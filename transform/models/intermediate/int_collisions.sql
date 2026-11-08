-- Car-to-car collisions noted by race control, one row per incident.
-- Format: "TURN 1 INCIDENT INVOLVING CARS 16 (LEC) AND 18 (STR) NOTED - CAUSING A COLLISION".
-- The stewards' follow-ups (UNDER INVESTIGATION, REVIEWED ...) repeat it and are left out.
with noted as (
    select
        session_key,
        message_at,
        lap_number,
        regexp_extract(message, 'INVOLVING CARS? (.*) NOTED', 1) as cars
    from {{ ref('stg_race_control') }}
    where message like '%INCIDENT INVOLVING CAR%NOTED - CAUSING A COLLISION%'
        and message not like 'FIA STEWARDS%'
)

select
    session_key,
    cars,
    -- Number of cars involved: one "(ABC)" code per car.
    length(cars) - length(replace(cars, '(', '')) as cars_involved,
    min(message_at) as noted_at,
    min(lap_number) as lap_number
from noted
group by session_key, cars
