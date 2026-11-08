-- Links each OpenF1 session to its Jolpica round. Dates can differ by a day (Las Vegas starts
-- Saturday night local, Sunday in UTC), so the match allows one day either way.
-- Only sessions with results count, so races not yet run (or not yet settled) don't show zeros.
select
    s.session_key,
    s.season,
    r.round,
    s.session_type,
    r.race_name,
    s.started_at
from {{ ref('stg_sessions') }} as s
inner join {{ ref('stg_races') }} as r
    on s.season = r.season
    and {{ dbt.datediff(
        "case when s.session_type = 'sprint' then r.sprint_date else r.race_date end",
        'cast(s.started_at as date)', 'day') }} between -1 and 1
where exists (
    select 1
    from {{ ref('stg_results') }} as res
    where res.season = r.season and res.round = r.round and res.session_type = s.session_type
)
