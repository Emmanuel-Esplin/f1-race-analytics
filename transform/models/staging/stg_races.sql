-- Calendar: one row per round.
select
    season,
    round,
    race_name,
    circuit_id,
    circuit_name,
    locality,
    country,
    cast(race_date as date) as race_date,
    cast(sprint_date as date) as sprint_date
from {{ silver('races') }}
