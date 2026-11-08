-- Drivers' championship table after each round.
select season, round, driver_id, driver_code, driver_name, constructor_id, position, points, wins
from {{ silver('driver_standings') }}
