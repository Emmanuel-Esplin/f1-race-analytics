-- Crashes and race time lost to them, per race and sprint (every session run, zeros included).
-- crashes = collisions noted by race control
--         + cars that stopped and brought out a SC, VSC or red flag, counted once per car even
--           when a Safety Car turns into a red flag, and not when already part of a collision.
with collisions as (
    select session_key, count(*) as collisions, sum(cars_involved) as cars_in_collisions
    from {{ ref('int_collisions') }}
    group by session_key
),

neutralisations as (
    select *
    from {{ ref('mart_neutralised_time') }}
),

stopped_cars as (
    select r.session_key, count(distinct r.driver_id) as stopped_cars
    from {{ ref('int_retirements') }} as r
    inner join neutralisations as n
        on r.session_key = n.session_key
        and r.stopped_on_lap between n.start_lap - 2 and n.start_lap + 1
    where not exists (
        select 1
        from {{ ref('int_collisions') }} as c
        where c.session_key = r.session_key
            and c.lap_number between r.stopped_on_lap - 2 and r.stopped_on_lap + 1
            and c.cars like '%(' || r.driver_code || ')%'
    )
    group by r.session_key
),

time_lost as (
    select
        session_key,
        sum(duration_min) as neutralised_min,
        sum(case when caused_by_crash then duration_min else 0 end) as crash_neutralised_min,
        sum(case when period_type = 'safety_car' then 1 else 0 end) as safety_cars,
        sum(case when period_type = 'vsc' then 1 else 0 end) as virtual_safety_cars,
        sum(case when period_type = 'red_flag' then 1 else 0 end) as red_flags
    from neutralisations
    group by session_key
)

select
    sr.season,
    sr.round,
    sr.race_name,
    sr.session_type,
    sr.session_key,
    cast(coalesce(c.collisions, 0) + coalesce(s.stopped_cars, 0) as integer) as crashes,
    cast(coalesce(c.collisions, 0) as integer) as collisions,
    cast(coalesce(c.cars_in_collisions, 0) as integer) as cars_in_collisions,
    cast(coalesce(s.stopped_cars, 0) as integer) as stopped_cars,
    cast(coalesce(t.safety_cars, 0) as integer) as safety_cars,
    cast(coalesce(t.virtual_safety_cars, 0) as integer) as virtual_safety_cars,
    cast(coalesce(t.red_flags, 0) as integer) as red_flags,
    round(coalesce(t.neutralised_min, 0), 1) as neutralised_min,
    round(coalesce(t.crash_neutralised_min, 0), 1) as time_lost_to_crashes_min
from {{ ref('int_session_rounds') }} as sr
left join collisions as c on sr.session_key = c.session_key
left join stopped_cars as s on sr.session_key = s.session_key
left join time_lost as t on sr.session_key = t.session_key
