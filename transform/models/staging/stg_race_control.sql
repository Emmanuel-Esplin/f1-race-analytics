-- Race-control messages; the message text is upper case in the feed.
select
    season,
    session_key,
    {{ iso_timestamp('message_at') }} as message_at,
    lap_number,
    category,
    flag,
    scope,
    sector,
    driver_number,
    upper(message) as message
from {{ silver('race_control') }}
