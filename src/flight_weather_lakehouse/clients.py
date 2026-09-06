import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from .config import Settings
from .domain import Airport


class SourceClientError(RuntimeError):
    pass


class OpenSkyClient:
    URL = "https://opensky-network.org/api/states/all"

    def __init__(self, settings: Settings):
        self.settings = settings

    async def fetch_states(self) -> dict[str, Any]:
        lon_min, lat_min, lon_max, lat_max = self.settings.bbox
        params = {"lamin": lat_min, "lomin": lon_min, "lamax": lat_max, "lomax": lon_max}
        auth = None
        if self.settings.opensky_username and self.settings.opensky_password:
            auth = (self.settings.opensky_username, self.settings.opensky_password)
        return await self._get_json(self.URL, params=params, auth=auth)

    async def _get_json(self, url: str, **kwargs: Any) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    response = await client.get(url, **kwargs)
                    response.raise_for_status()
                    return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                await asyncio.sleep(2**attempt)
        raise SourceClientError(f"OpenSky request failed after retries: {last_error}")


class OpenMeteoClient:
    def __init__(self, settings: Settings):
        self.url = settings.weather_api_url

    async def fetch_current(self, airport: Airport) -> dict[str, Any]:
        params = {
            "latitude": airport.latitude,
            "longitude": airport.longitude,
            "current": "temperature_2m,relative_humidity_2m,precipitation,rain,weather_code,cloud_cover,wind_speed_10m,wind_direction_10m",
            "timezone": "UTC",
        }
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    response = await client.get(self.url, params=params)
                    response.raise_for_status()
                    payload = response.json()
                    payload["airport"] = airport.icao
                    payload["collected_at"] = datetime.now(UTC).isoformat()
                    return payload
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                await asyncio.sleep(2**attempt)
        raise SourceClientError(f"Open-Meteo request failed after retries: {last_error}")

