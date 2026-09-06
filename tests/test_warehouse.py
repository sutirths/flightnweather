from flight_weather_lakehouse.config import Settings
from flight_weather_lakehouse.demo import write_demo_data
from flight_weather_lakehouse.lake import LocalLake
from flight_weather_lakehouse.pipeline import Pipeline
from flight_weather_lakehouse.warehouse import DuckDBWarehouse


def test_loader_is_idempotent_and_serves_data(tmp_path):
    lake = LocalLake(tmp_path / "lake")
    warehouse = DuckDBWarehouse(tmp_path / "warehouse.duckdb")
    settings = Settings(local_lake_path=tmp_path / "lake", duckdb_path=tmp_path / "warehouse.duckdb")
    write_demo_data(lake)
    pipeline = Pipeline(settings, lake, warehouse)
    result = pipeline.load()
    assert result == {"objects": 6, "flights": 3, "weather": 5, "skipped": 0}
    assert pipeline.load()["objects"] == 0
    assert len(warehouse.recent_flights(10)) == 3
    assert warehouse.latest_weather("KORD")[0]["airport"] == "KORD"
    assert warehouse.weather_impact(24)
