-- Car number to driver code for one session. Car numbers are only unique within a session.
select season, session_key, driver_number, name_acronym as driver_code, full_name, team_name
from {{ silver('drivers') }}
