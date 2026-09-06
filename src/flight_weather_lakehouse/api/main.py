from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

from fastapi import FastAPI, Query
from pydantic import BaseModel

from ..config import get_settings
from ..warehouse import build_warehouse


def warehouse():
    settings = get_settings()
    return build_warehouse(settings.warehouse_provider, settings.duckdb_path, settings.bigquery_project, settings.bigquery_dataset)


@asynccontextmanager
async def lifespan(_: FastAPI):
    warehouse().initialize()
    yield


app = FastAPI(
    title="Flight & Weather Lakehouse API",
    version="0.1.0",
    description="Read-only analytics API over the processed flight/weather warehouse.",
    lifespan=lifespan,
)


class Health(BaseModel):
    status: str
    timestamp: datetime
    warehouse_provider: str


@app.get("/v1/health", response_model=Health, tags=["Operations"])
def health() -> Health:
    settings = get_settings()
    return Health(status="ok", timestamp=datetime.now().astimezone(), warehouse_provider=settings.warehouse_provider)


@app.get("/v1/flights/recent", tags=["Flights"])
def recent_flights(limit: Annotated[int, Query(ge=1, le=500)] = 100) -> list[dict[str, Any]]:
    return warehouse().recent_flights(limit)


@app.get("/v1/weather/latest", tags=["Weather"])
def latest_weather(airport: Annotated[str | None, Query(min_length=4, max_length=4)] = None) -> list[dict[str, Any]]:
    return warehouse().latest_weather(airport.upper() if airport else None)


@app.get("/v1/analytics/weather-impact", tags=["Analytics"])
def weather_impact(hours: Annotated[int, Query(ge=1, le=720)] = 24) -> list[dict[str, Any]]:
    return warehouse().weather_impact(hours)

