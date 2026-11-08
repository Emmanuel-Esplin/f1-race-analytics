-- The leader at the end of each lap, and whether the lead changed hands on that lap.
with leaders as (
    select season, round, lap, driver_id
    from {{ ref('stg_lap_positions') }}
    where position = 1
)

select
    season,
    round,
    lap,
    driver_id,
    case
        when lag(driver_id) over (partition by season, round order by lap) is null then false
        else lag(driver_id) over (partition by season, round order by lap) <> driver_id
    end as lead_changed
from leaders
