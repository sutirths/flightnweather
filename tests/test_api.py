from fastapi.testclient import TestClient

from flight_weather_lakehouse.api.main import app


def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

