-- OpenF1 race and sprint sessions, with UTC start and end.
select
    season,
    session_key,
    meeting_key,
    case when session_name = 'Sprint' then 'sprint' else 'race' end as session_type,
    {{ iso_timestamp('date_start') }} as started_at,
    {{ iso_timestamp('date_end') }} as ended_at,
    country_name,
    location,
    circuit_short_name
from {{ silver('sessions') }}
