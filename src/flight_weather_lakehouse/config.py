from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "local"
    log_level: str = "INFO"
    poll_interval_seconds: int = Field(default=300, ge=30)
    lake_provider: str = "local"
    local_lake_path: Path = Path("data/lake")
    aws_s3_bucket: str | None = None
    aws_region: str = "us-east-1"
    warehouse_provider: str = "duckdb"
    duckdb_path: Path = Path("data/warehouse/flight_weather.duckdb")
    bigquery_project: str | None = None
    bigquery_dataset: str = "flight_weather"
    opensky_username: str | None = None
    opensky_password: str | None = None
    opensky_bbox: str = "-125.0,24.0,-66.0,49.0"
    weather_api_url: str = "https://api.open-meteo.com/v1/forecast"

    @field_validator("lake_provider")
    @classmethod
    def validate_lake(cls, value: str) -> str:
        if value not in {"local", "s3"}:
            raise ValueError("LAKE_PROVIDER must be local or s3")
        return value

    @field_validator("warehouse_provider")
    @classmethod
    def validate_warehouse(cls, value: str) -> str:
        if value not in {"duckdb", "bigquery"}:
            raise ValueError("WAREHOUSE_PROVIDER must be duckdb or bigquery")
        return value

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        values = tuple(float(value) for value in self.opensky_bbox.split(","))
        if len(values) != 4:
            raise ValueError("OPENSKY_BBOX requires lon_min,lat_min,lon_max,lat_max")
        return values  # type: ignore[return-value]


@lru_cache
def get_settings() -> Settings:
    return Settings()

