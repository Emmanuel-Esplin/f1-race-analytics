-- Every lap of every race has exactly one leader, so laps led add up to the race distance.
select season, round, sum(laps_led) as laps_led, max(race_laps) as race_laps
from {{ ref('mart_lap_leaders') }}
group by season, round
having sum(laps_led) <> max(race_laps)
