-- Cars that retired from a race or sprint, and the lap they stopped on.
-- Jolpica doesn't say why (nearly all are just "Retired"), so this alone is not a crash.
select
    sr.session_key,
    r.season,
    r.round,
    r.session_type,
    r.driver_id,
    r.driver_code,
    r.driver_number,
    r.status,
    r.laps + 1 as stopped_on_lap
from {{ ref('stg_results') }} as r
inner join {{ ref('int_session_rounds') }} as sr
    on r.season = sr.season and r.round = sr.round and r.session_type = sr.session_type
where r.status not in ('Finished', 'Lapped', 'Disqualified', 'Did not start', 'Withdrew')
    and r.status not like '+%'
