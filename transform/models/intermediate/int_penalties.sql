-- Penalties handed out in races and sprints, one row per penalty.
-- Format: "FIA STEWARDS: 5 SECOND TIME PENALTY FOR CAR 55 (SAI) - CAUSING A COLLISION (12:34:56)".
-- "PENALTY SERVED - ..." lines repeat an earlier penalty and are left out.
{% set pattern = "^FIA STEWARDS: (\\d+ SECOND TIME|\\d+ SECOND STOP/GO|STOP-AND-GO|DRIVE THROUGH) PENALTY FOR CAR (\\d+) \\(([A-Z]{3})\\)(?: - (.*))?$" %}
with parsed as (
    select
        session_key,
        message_at,
        lap_number,
        regexp_extract(message, '{{ pattern }}', 1) as penalty_text,
        cast(regexp_extract(message, '{{ pattern }}', 2) as integer) as driver_number,
        regexp_extract(message, '{{ pattern }}', 3) as driver_code,
        -- The reason sometimes ends in the time of the offence, e.g. " (12:34:56)".
        trim(regexp_replace(
            coalesce(regexp_extract(message, '{{ pattern }}', 4), ''), ' \(\d+:\d+:\d+\)$', ''
        )) as reason
    from {{ ref('stg_race_control') }}
    where coalesce(regexp_extract(message, '{{ pattern }}', 0), '') <> ''
),

typed as (
    select
        session_key,
        message_at,
        lap_number,
        driver_number,
        driver_code,
        case
            when penalty_text like '%TIME' then 'time'
            when penalty_text = 'DRIVE THROUGH' then 'drive_through'
            else 'stop_go'
        end as penalty_type,
        case
            when penalty_text like '%SECOND%'
                then cast(regexp_extract(penalty_text, '^(\d+)', 1) as integer)
        end as penalty_seconds,
        nullif(reason, '') as reason
    from parsed
)

-- A repeated message (an UPDATE or a re-send) is the same penalty: keep the first.
select
    session_key,
    driver_number,
    driver_code,
    penalty_type,
    penalty_seconds,
    reason,
    min(message_at) as issued_at,
    min(lap_number) as lap_number
from typed
group by session_key, driver_number, driver_code, penalty_type, penalty_seconds, reason
