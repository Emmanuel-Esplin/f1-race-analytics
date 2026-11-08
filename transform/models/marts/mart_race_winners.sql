-- Winner of every race and sprint, with the margin to second place.
with podium as (
    select *
    from {{ ref('stg_results') }}
    where position in (1, 2)
)

select
    w.season,
    w.round,
    r.race_name,
    w.session_type,
    case when w.session_type = 'sprint' then r.sprint_date else r.race_date end as session_date,
    w.driver_id,
    w.driver_code,
    w.driver_name,
    w.constructor_name,
    w.grid,
    w.laps,
    w.time_millis as winning_time_ms,
    -- Null when second place was lapped, because then there is no time gap.
    s.time_millis - w.time_millis as margin_to_second_ms
from podium as w
inner join {{ ref('stg_races') }} as r
    on w.season = r.season and w.round = r.round
left join podium as s
    on w.season = s.season
    and w.round = s.round
    and w.session_type = s.session_type
    and s.position = 2
where w.position = 1
