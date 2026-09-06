-- OpenSky reports positions rather than commercial arrival times. This is a weather
-- exposure mart, not a claim of causal carrier delay.
with weather as (
    select
        airport,
        observed_hour,
        max(precipitation_mm) as precipitation_mm,
        max(wind_speed_kph) as wind_speed_kph,
        max(cloud_cover) as cloud_cover,
        bool_or(adverse_weather) as adverse_weather
    from {{ ref('stg_weather') }}
    group by 1, 2
),
flights as (
    select
        date_trunc('hour', observed_at) as observed_hour,
        count(*) as tracked_flight_states,
        count(distinct icao24) as distinct_aircraft
    from {{ ref('stg_flights') }}
    group by 1
)
select
    weather.airport,
    weather.observed_hour,
    coalesce(flights.tracked_flight_states, 0) as tracked_flight_states,
    coalesce(flights.distinct_aircraft, 0) as distinct_aircraft,
    weather.precipitation_mm,
    weather.wind_speed_kph,
    weather.cloud_cover,
    weather.adverse_weather
from weather
left join flights using (observed_hour)

