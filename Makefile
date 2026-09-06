.PHONY: install ingest run-pipeline api test lint dbt-run docker-up

install:
	python -m pip install -e '.[dev,dbt]'

ingest:
	flight-weather ingest

run-pipeline:
	flight-weather pipeline --once

api:
	uvicorn flight_weather_lakehouse.api.main:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest -q

lint:
	ruff check src tests

dbt-run:
	cd dbt && dbt deps && dbt build --profiles-dir .

docker-up:
	docker compose up --build

