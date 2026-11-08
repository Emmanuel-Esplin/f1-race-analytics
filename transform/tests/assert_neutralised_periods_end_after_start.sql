-- Every neutralised period must end, and after it starts. A failure means a new race-control
-- message format (as when 2026 renamed the VSC message) is not handled.
select session_key, period_type, started_at, duration_min
from {{ ref('mart_neutralised_time') }}
where duration_min is null or duration_min <= 0 or duration_min > 180
