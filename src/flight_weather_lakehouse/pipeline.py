import asyncio
import logging
import uuid
from datetime import UTC, datetime

from .clients import OpenMeteoClient, OpenSkyClient
from .config import Settings
from .domain import AIRPORTS
from .lake import Lake
from .warehouse import Warehouse

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, settings: Settings, lake: Lake, warehouse: Warehouse):
        self.settings, self.lake, self.warehouse = settings, lake, warehouse

    async def ingest(self) -> list[str]:
        run_id = uuid.uuid4().hex
        observed_at = datetime.now(UTC)
        opensky, weather = OpenSkyClient(self.settings), OpenMeteoClient(self.settings)
        flight_payload, weather_results = await asyncio.gather(
            opensky.fetch_states(),
            asyncio.gather(*(weather.fetch_current(airport) for airport in AIRPORTS), return_exceptions=True),
        )
        keys = [self.lake.put("opensky", "flight_states", flight_payload, observed_at)]
        for item in weather_results:
            if isinstance(item, Exception):
                logger.warning("weather_fetch_failed", extra={"error": str(item), "run_id": run_id})
                continue
            keys.append(self.lake.put("open_meteo", "weather_observation", item, observed_at))
        logger.info("ingestion_complete run_id=%s object_count=%s", run_id, len(keys))
        return keys

    def load(self) -> dict[str, int]:
        totals = {"objects": 0, "flights": 0, "weather": 0, "skipped": 0}
        self.warehouse.initialize()
        for key in self.lake.list_objects():
            if self.warehouse.is_loaded(key):
                totals["skipped"] += 1
                continue
            payload = self.lake.get(key)
            if "/entity=flight_states/" in key:
                totals["flights"] += self.warehouse.load_flights(key, payload)
            elif "/entity=weather_observation/" in key:
                totals["weather"] += self.warehouse.load_weather(key, payload)
            else:
                logger.warning("unknown_lake_object key=%s", key)
                continue
            totals["objects"] += 1
        logger.info("load_complete %s", totals)
        return totals

    async def run_once(self) -> dict[str, int]:
        await self.ingest()
        return self.load()

    async def run_forever(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.exception("pipeline_cycle_failed")
            await asyncio.sleep(self.settings.poll_interval_seconds)

