-- Penalties per driver per season, by type.
select
    season,
    driver_id,
    driver_code,
    driver_name,
    count(*) as penalties,
    cast(sum(case when penalty_type = 'time' then 1 else 0 end) as bigint) as time_penalties,
    cast(coalesce(sum(penalty_seconds), 0) as bigint) as penalty_seconds,
    cast(sum(case when penalty_type = 'drive_through' then 1 else 0 end) as bigint) as drive_throughs,
    cast(sum(case when penalty_type = 'stop_go' then 1 else 0 end) as bigint) as stop_gos,
    cast(sum(case when reason like '%COLLISION%' then 1 else 0 end) as bigint) as for_collisions,
    cast(sum(case when reason like '%TRACK LIMITS%' then 1 else 0 end) as bigint) as for_track_limits,
    cast(sum(case when reason like '%PIT LANE%' then 1 else 0 end) as bigint) as for_pit_lane_speeding,
    count(distinct round) as races_penalised
from {{ ref('mart_penalties') }}
group by season, driver_id, driver_code, driver_name
