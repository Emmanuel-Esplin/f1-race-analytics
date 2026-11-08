-- Each championship has exactly one leader after every round.
select season, round, championship, count(*) as leaders
from {{ ref('mart_championship_progression') }}
where is_leader
group by season, round, championship
having count(*) <> 1
