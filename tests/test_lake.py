from datetime import UTC, datetime

from flight_weather_lakehouse.lake import LocalLake


def test_local_lake_round_trip(tmp_path):
    lake = LocalLake(tmp_path)
    key = lake.put("test", "events", {"id": 1}, datetime(2026, 1, 1, tzinfo=UTC))
    assert key.startswith("raw/source=test/entity=events/dt=2026-01-01/")
    assert lake.list_objects() == [key]
    assert lake.get(key) == {"id": 1}

