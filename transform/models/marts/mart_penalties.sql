-- Every penalty handed out during a race or sprint, with the driver and round.
with drivers as (
    select distinct season, driver_code, driver_id, driver_name
    from {{ ref('stg_results') }}
)

select
    sr.season,
    sr.round,
    sr.race_name,
    sr.session_type,
    d.driver_id,
    p.driver_code,
    d.driver_name,
    p.penalty_type,
    p.penalty_seconds,
    p.reason,
    p.lap_number,
    p.issued_at
from {{ ref('int_penalties') }} as p
inner join {{ ref('int_session_rounds') }} as sr on p.session_key = sr.session_key
left join drivers as d on sr.season = d.season and p.driver_code = d.driver_code
