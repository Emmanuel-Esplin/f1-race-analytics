-- Drivers' and constructors' standings after every round, with the gap to the leader.
with standings as (
    select
        season, round, 'drivers' as championship, driver_id as competitor_id,
        driver_name as competitor_name, position, points, wins
    from {{ ref('stg_driver_standings') }}
    union all
    select
        season, round, 'constructors' as championship, constructor_id as competitor_id,
        constructor_name as competitor_name, position, points, wins
    from {{ ref('stg_constructor_standings') }}
),

leaders as (
    select season, round, championship, competitor_name as leader_name, points as leader_points
    from standings
    where position = 1
)

select
    s.season,
    s.round,
    r.race_name,
    s.championship,
    s.competitor_id,
    s.competitor_name,
    s.position,
    s.points,
    s.wins,
    s.position = 1 as is_leader,
    l.leader_name,
    l.leader_points - s.points as points_behind_leader
from standings as s
inner join leaders as l
    on s.season = l.season and s.round = l.round and s.championship = l.championship
inner join {{ ref('stg_races') }} as r on s.season = r.season and s.round = r.round
