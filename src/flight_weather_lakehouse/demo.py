from datetime import UTC, datetime

from .domain import AIRPORTS
from .lake import Lake


def write_demo_data(lake: Lake) -> list[str]:
    """Write a deterministic data set that follows the live sources' payload contracts."""
    now = datetime.now(UTC).replace(microsecond=0)
    states = [
        ["a1b2c3", "UAL123  ", "United States", int(now.timestamp()), int(now.timestamp()), -87.90, 41.98, 3200.0, False, 225.0, 90.0, 0.0, None, 3400.0, "1234", False, 0],
        ["d4e5f6", "DAL456  ", "United States", int(now.timestamp()), int(now.timestamp()), -73.79, 40.64, 4900.0, False, 210.0, 270.0, -1.0, None, 5100.0, "5678", False, 0],
        ["f7e8d9", "AAL789  ", "United States", int(now.timestamp()), int(now.timestamp()), -118.42, 33.94, 1600.0, False, 175.0, 180.0, -2.0, None, 1700.0, "4321", False, 0],
    ]
    keys = [lake.put("opensky", "flight_states", {"time": int(now.timestamp()), "states": states}, now)]
    for index, airport in enumerate(AIRPORTS):
        current = {
            "time": now.isoformat(), "temperature_2m": 17.0 + index, "relative_humidity_2m": 60,
            "precipitation": 1.8 if airport.icao == "KORD" else 0.0,
            "rain": 1.8 if airport.icao == "KORD" else 0.0, "weather_code": 63 if airport.icao == "KORD" else 1,
            "cloud_cover": 85 if airport.icao == "KORD" else 15, "wind_speed_10m": 38 if airport.icao == "KORD" else 12,
            "wind_direction_10m": 270,
        }
        keys.append(lake.put("open_meteo", "weather_observation", {"airport": airport.icao, "collected_at": now.isoformat(), "latitude": airport.latitude, "longitude": airport.longitude, "current": current}, now))
    return keys

