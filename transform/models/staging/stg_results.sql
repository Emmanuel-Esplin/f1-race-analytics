-- Classified results of every race and sprint. position is null for non-finishers.
select
    season,
    round,
    session_type,
    driver_id,
    driver_code,
    driver_number,
    driver_name,
    constructor_id,
    constructor_name,
    grid,
    position,
    position_text,
    points,
    laps,
    status,
    time_millis,
    gap_text
from {{ silver('results') }}
