with source as (
    select * from {{ source('raw', 'raw_weather_observations') }}
)
select
    event_id,
    airport,
    observed_at,
    date_trunc('hour', observed_at) as observed_hour,
    temperature_c,
    relative_humidity,
    precipitation_mm,
    rain_mm,
    weather_code,
    cloud_cover,
    wind_speed_kph,
    case
        when precipitation_mm > 0 or wind_speed_kph >= 30 or weather_code in (65, 75, 95, 96, 99)
        then true else false
    end as adverse_weather
from source

