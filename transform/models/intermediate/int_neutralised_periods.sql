-- Every Safety Car, Virtual Safety Car and red-flag period, with start, end and duration.
-- A caution (SC or VSC) runs from DEPLOYED to the next TRACK CLEAR (the green flag), or until a
-- red flag takes over. A red flag runs from RED FLAG or SESSION ABORTED (the feed has used both)
-- to the restart (SESSION STARTED). 2026 renamed VIRTUAL SAFETY CAR DEPLOYED to VSC DEPLOYED.
-- Messages after SESSION FINISHED (e.g. a red flag shown after the chequered flag) are ignored.
with messages as (
    select session_key, message_at, lap_number, message
    from {{ ref('stg_race_control') }}
),

finished as (
    select session_key, min(message_at) as finished_at
    from messages
    where message = 'SESSION FINISHED'
    group by session_key
),

starts as (
    select
        m.session_key,
        m.message_at as started_at,
        m.lap_number as start_lap,
        case
            when m.message in ('RED FLAG', 'SESSION ABORTED') then 'red_flag'
            when m.message like '%VIRTUAL SAFETY CAR DEPLOYED%' then 'vsc'
            when m.message like '%VSC DEPLOYED%' then 'vsc'
            else 'safety_car'
        end as period_type
    from messages as m
    left join finished as f on m.session_key = f.session_key
    where (
        m.message like '%SAFETY CAR DEPLOYED%'
        or m.message like '%VSC DEPLOYED%'
        or m.message in ('RED FLAG', 'SESSION ABORTED')
    )
    and (f.finished_at is null or m.message_at < f.finished_at)
),

ends as (
    select
        session_key,
        message_at as ended_at,
        lap_number as end_lap,
        message in ('TRACK CLEAR', 'RED FLAG', 'SESSION ABORTED', 'SESSION FINISHED') as ends_caution,
        message in ('SESSION STARTED', 'SESSION FINISHED') as ends_red_flag
    from messages
    where message in (
        'TRACK CLEAR', 'RED FLAG', 'SESSION ABORTED', 'SESSION STARTED', 'SESSION FINISHED'
    )
),

-- The first message after each start that can end that kind of period.
paired as (
    select
        s.session_key,
        s.period_type,
        s.started_at,
        s.start_lap,
        min(e.ended_at) as ended_at
    from starts as s
    left join ends as e
        on s.session_key = e.session_key
        and e.ended_at > s.started_at
        and (
            (s.period_type = 'red_flag' and e.ends_red_flag)
            or (s.period_type <> 'red_flag' and e.ends_caution)
        )
    group by s.session_key, s.period_type, s.started_at, s.start_lap
),

-- Race control sometimes repeats DEPLOYED; repeats share an end, so keep the earliest start.
periods as (
    select
        session_key,
        period_type,
        min(started_at) as started_at,
        min(start_lap) as start_lap,
        ended_at
    from paired
    group by session_key, period_type, ended_at
)

select
    p.session_key,
    p.period_type,
    p.started_at,
    p.ended_at,
    p.start_lap,
    e.end_lap,
    {{ seconds_between('p.started_at', 'p.ended_at') }} as duration_s
from periods as p
-- Two end messages can share a timestamp, so take one end lap per moment.
left join (
    select session_key, ended_at, min(end_lap) as end_lap
    from ends
    group by session_key, ended_at
) as e
    on p.session_key = e.session_key and p.ended_at = e.ended_at
