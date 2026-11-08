-- Constructors' championship table after each round.
select season, round, constructor_id, constructor_name, position, points, wins
from {{ silver('constructor_standings') }}
