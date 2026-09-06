# Flight & Weather Data Lakehouse

A portfolio-ready, production-shaped data pipeline that correlates near-real-time OpenSky flight state vectors with Open-Meteo weather observations. It follows the same lake → warehouse → transformation → serving pattern used in travel and logistics data platforms.

```text
OpenSky + Open-Meteo → immutable JSON lake (local/S3) → DuckDB/BigQuery raw tables
     → dbt staging + marts → FastAPI analytics endpoints
```

## What is included

- API clients with retries, timeouts, and typed models
- Immutable, partitioned raw JSON records in local storage or AWS S3
- Idempotent loading into DuckDB locally; an optional BigQuery adapter
- A dbt project that produces cleaned flight/weather tables and a weather-impact mart
- FastAPI health, recent-flight, weather, and analytics endpoints with OpenAPI docs
- Polling scheduler, Docker Compose, tests, linting, and a GitHub Actions workflow

## Quick start

Requires Python 3.11+.

```bash
cp .env.example .env
make install
make run-pipeline        # one collection + load cycle
make dbt-run             # optional: builds analytical dbt models
make api
```

Open `http://localhost:8000/docs`. The default configuration writes to `data/lake` and `data/warehouse/flight_weather.duckdb`, so no cloud account is necessary for a demo. Anonymous OpenSky access is rate limited; add credentials to `.env` for more reliable polling.

## Commands

```bash
flight-weather ingest             # fetch and save raw flight + weather API responses
flight-weather load               # load every raw object not already loaded
flight-weather pipeline --once    # ingest then load once
flight-weather pipeline           # poll forever at POLL_INTERVAL_SECONDS
flight-weather bootstrap-demo     # deterministic local data for screenshots/demo
```

`bootstrap-demo` is useful when APIs are unavailable or before a portfolio walkthrough. It writes realistic but synthetic records through the same raw-load path.

## Cloud deployment

### AWS data lake

Set `LAKE_PROVIDER=s3`, `AWS_S3_BUCKET`, and `AWS_REGION`; authenticate with standard AWS credentials (profile, environment, IAM role, or workload identity). Raw objects are written as:

```text
raw/source=opensky/entity=flight_states/dt=YYYY-MM-DD/hour=HH/<timestamp>_<uuid>.json
```

Use an IAM role limited to `s3:PutObject`, `s3:GetObject`, and `s3:ListBucket` for that bucket/prefix. Apply S3 lifecycle rules to transition raw data to cheaper storage.

### BigQuery warehouse

Set `WAREHOUSE_PROVIDER=bigquery`, `BIGQUERY_PROJECT`, and `BIGQUERY_DATASET`, install `pip install -e '.[bigquery]'`, then use a service account/workload identity with BigQuery Job User and dataset Editor roles. The loader creates raw tables and uses a stable event ID for duplicate protection. Point dbt at BigQuery by adding a target to `dbt/profiles.yml`.

For production, run `flight-weather pipeline --once` in Cloud Run Jobs, ECS/Fargate, or Kubernetes CronJobs every 5 minutes. Keep API serving separate from the collector; this Compose file does that already.

## Data model

| Layer | Relation | Purpose |
|---|---|---|
| Lake | raw JSON | Replayable source responses, partitioned by source/entity/date/hour |
| Raw | `raw_flight_states`, `raw_weather_observations` | Flattened, idempotently loaded records |
| dbt staging | `stg_flights`, `stg_weather` | Validated, normalized analytics inputs |
| dbt mart | `mart_weather_flight_impact` | Weather-to-flight-state analysis by airport/hour |

OpenSky state vectors report airborne position and velocity, not commercial arrival/departure delay. The mart therefore exposes **adverse-weather flight exposure** rather than claiming true carrier delays. Substitute a schedule/arrival feed (Aviationstack, Cirium, BTS, etc.) to model actual arrival delay.

## API examples

```bash
curl http://localhost:8000/v1/health
curl 'http://localhost:8000/v1/flights/recent?limit=25'
curl 'http://localhost:8000/v1/analytics/weather-impact?hours=24'
curl 'http://localhost:8000/v1/weather/latest?airport=KORD'
```

## Quality and operations

```bash
make test
make lint
docker compose up --build
```

Logs are structured JSON and include a `run_id`. The warehouse keeps a `loaded_objects` ledger, so retries do not duplicate a lake object. Put secrets in your cloud secret manager—never in source control. Monitoring recommendations: alert on stale source timestamps, API failure rate, loader lag, and raw-to-warehouse object-count mismatch.

## Portfolio notes

Before publishing, replace the author name, add a diagram screenshot from this README, and deploy the API to a public URL. Include a short screen recording of `/docs`, S3 object partitions, a dbt lineage graph, and a dashboard built from `mart_weather_flight_impact`.

