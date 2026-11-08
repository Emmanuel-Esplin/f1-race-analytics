-- Running order at the end of every lap of every race.
select season, round, lap, driver_id, position, lap_time_ms
from {{ silver('lap_positions') }}
