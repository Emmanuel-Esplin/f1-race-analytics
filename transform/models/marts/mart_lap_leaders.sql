-- Laps led per driver per race. Sum laps_led over a season for season totals.
with race_laps as (
    select season, round, max(lap) as race_laps, cast(sum(case when lead_changed then 1 else 0 end) as integer) as lead_changes
    from {{ ref('int_lap_leaders') }}
    group by season, round
),

drivers as (
    select distinct season, round, driver_id, driver_code, driver_name, constructor_name
    from {{ ref('stg_results') }}
    where session_type = 'race'
)

select
    l.season,
    l.round,
    r.race_name,
    l.driver_id,
    d.driver_code,
    d.driver_name,
    d.constructor_name,
    count(*) as laps_led,
    min(l.lap) as first_lap_led,
    rl.race_laps,
    round(100.0 * count(*) / rl.race_laps, 1) as pct_laps_led,
    rl.lead_changes as race_lead_changes
from {{ ref('int_lap_leaders') }} as l
inner join race_laps as rl on l.season = rl.season and l.round = rl.round
inner join {{ ref('stg_races') }} as r on l.season = r.season and l.round = r.round
left join drivers as d
    on l.season = d.season and l.round = d.round and l.driver_id = d.driver_id
group by
    l.season, l.round, r.race_name, l.driver_id, d.driver_code, d.driver_name,
    d.constructor_name, rl.race_laps, rl.lead_changes
