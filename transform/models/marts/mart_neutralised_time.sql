-- Every Safety Car, VSC and red-flag period, and whether a crash caused it.
-- Cause: a collision noted, or a car retiring, from two laps before the period started to one
-- lap after (race control often notes the collision just after the Safety Car comes out).
-- Retirements don't say why a car stopped, so a breakdown that brings out a Safety Car counts too.
with periods as (
    select p.*, sr.season, sr.round, sr.session_type, sr.race_name
    from {{ ref('int_neutralised_periods') }} as p
    inner join {{ ref('int_session_rounds') }} as sr on p.session_key = sr.session_key
),

collisions as (
    select p.session_key, p.started_at, count(*) as collisions
    from periods as p
    inner join {{ ref('int_collisions') }} as c
        on p.session_key = c.session_key
        and c.lap_number between p.start_lap - 2 and p.start_lap + 1
    group by p.session_key, p.started_at
),

retirements as (
    select p.session_key, p.started_at, count(*) as retirements
    from periods as p
    inner join {{ ref('int_retirements') }} as r
        on p.session_key = r.session_key
        and r.stopped_on_lap between p.start_lap - 2 and p.start_lap + 1
    group by p.session_key, p.started_at
)

select
    p.season,
    p.round,
    p.race_name,
    p.session_type,
    p.session_key,
    p.period_type,
    p.started_at,
    p.ended_at,
    p.start_lap,
    p.end_lap,
    round(p.duration_s / 60.0, 2) as duration_min,
    case
        when coalesce(c.collisions, 0) > 0 then 'collision'
        when coalesce(r.retirements, 0) > 0 then 'car_stopped'
        else 'other'
    end as cause,
    coalesce(c.collisions, 0) > 0 or coalesce(r.retirements, 0) > 0 as caused_by_crash
from periods as p
left join collisions as c on p.session_key = c.session_key and p.started_at = c.started_at
left join retirements as r on p.session_key = r.session_key and p.started_at = r.started_at
