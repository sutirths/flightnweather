with source as (
    select * from {{ source('raw', 'raw_flight_states') }}
)
select
    event_id,
    observed_at,
    icao24,
    nullif(trim(callsign), '') as callsign,
    origin_country,
    longitude,
    latitude,
    baro_altitude as altitude_meters,
    round(velocity * 3.6, 1) as velocity_kph,
    true_track,
    vertical_rate,
    on_ground
from source
where latitude between -90 and 90
  and longitude between -180 and 180

