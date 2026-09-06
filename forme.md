# Flight & Weather Data Lakehouse — Interview Guide

## 30-second introduction

I built a production-style data lakehouse that collects near-real-time aircraft position data and airport weather, preserves the raw API responses in a data lake, loads normalized records into a warehouse, transforms them with dbt, and serves analytics through a FastAPI service. The purpose is to demonstrate an end-to-end data engineering workflow similar to what a travel, airline, or logistics company would use to monitor operational conditions.

The project can run entirely locally with filesystem storage and DuckDB, but its interfaces support AWS S3 for the data lake and Google BigQuery for the warehouse. This makes it easy to demo without cloud costs while retaining a clear production path.

## Problem it solves

Airlines and logistics organizations need timely visibility into conditions that affect operations. Flight activity alone does not explain disruption risk; weather alone does not show operational exposure. This project brings both into one analytical system.

It answers questions such as:

- What aircraft are currently being tracked?
- What are the latest weather conditions at configured airports?
- During which airport-hours was weather adverse, based on precipitation, wind, cloud cover, and weather codes?
- How much tracked flight activity occurred during those periods?

The project deliberately calls this **weather exposure**, not delay prediction. OpenSky provides state vectors (position, altitude, velocity) rather than schedule, departure, arrival, and delay data. Claiming it calculates airline delays would be inaccurate. A schedule or actual-arrival feed can be added later to calculate true delay impact.

## Architecture

```text
                         ┌─────────────────────┐
                         │ OpenSky REST API    │
                         │ flight state vectors│
                         └─────────┬───────────┘
                                   │
┌─────────────────────┐            │            ┌─────────────────────┐
│ Open-Meteo REST API │────────────┼───────────►│ Python collector    │
│ current airport data│            │            │ retries + timeouts  │
└─────────────────────┘            │            └─────────┬───────────┘
                                                         │
                                               ┌─────────▼───────────┐
                                               │ Raw data lake        │
                                               │ local files or S3    │
                                               └─────────┬───────────┘
                                                         │
                                               ┌─────────▼───────────┐
                                               │ Idempotent loader    │
                                               │ JSON → tabular rows  │
                                               └─────────┬───────────┘
                                                         │
                    ┌────────────────────────────────────▼───────────────────────────────────┐
                    │ Warehouse: DuckDB locally / BigQuery in cloud                            │
                    │ raw_flight_states | raw_weather_observations | loaded_objects            │
                    └────────────────────────────────────┬───────────────────────────────────┘
                                                         │
                                               ┌─────────▼───────────┐
                                               │ dbt                 │
                                               │ staging + mart      │
                                               └─────────┬───────────┘
                                                         │
                                               ┌─────────▼───────────┐
                                               │ FastAPI             │
                                               │ analytics endpoints │
                                               └─────────────────────┘
```

## Technology stack

| Area | Technology | Why it is used |
|---|---|---|
| Language | Python 3.11+ | Strong ecosystem for API integration, orchestration, and analytics. |
| Flight source | OpenSky Network REST API | Free near-real-time aircraft state-vector data. |
| Weather source | Open-Meteo REST API | Free current weather data without an API key. |
| HTTP | `httpx` | Asynchronous API requests, explicit timeouts, and retry handling. |
| Configuration | Pydantic Settings | Validated environment-based configuration and safe secret separation. |
| Data lake | Local filesystem / AWS S3 | Local mode enables no-cost demos; S3 is the cloud production option. |
| Warehouse | DuckDB / Google BigQuery | DuckDB is lightweight for local analytics; BigQuery supports cloud-scale SQL. |
| Transformations | dbt + SQL | Versioned, testable analytical models separate from ingestion code. |
| Serving | FastAPI | High-performance, typed REST API with automatic OpenAPI documentation. |
| Containers | Docker + Docker Compose | Reproducible API and collector processes. |
| Infrastructure | Terraform | Defines a secure S3 raw-data lake with encryption and lifecycle rules. |
| Quality | pytest, Ruff, GitHub Actions | Tests, linting, and CI on pushes and pull requests. |

## Data sources

### OpenSky

The collector calls OpenSky’s `states/all` endpoint for a configurable geographic bounding box. Each state vector includes fields such as:

- ICAO24 aircraft identifier
- Callsign
- Origin country
- Last position time
- Longitude and latitude
- Barometric and geometric altitude
- Ground/airborne state
- Velocity, heading, and vertical rate
- Transponder squawk and position source

Anonymous access is rate limited. The project supports optional credentials through `OPENSKY_USERNAME` and `OPENSKY_PASSWORD`; credentials must be stored in `.env` or a cloud secret manager, never committed.

### Open-Meteo

The collector retrieves current weather for five configured airports: KJFK, KORD, KDFW, KLAX, and KATL. The payload includes temperature, humidity, precipitation, rain, weather code, cloud cover, wind speed, and wind direction.

The airport list is intentionally small and explicit in `domain.py` for a simple demo. In production, it would come from a managed airport reference table.

## End-to-end process

### 1. Collect

`Pipeline.ingest()` concurrently requests:

1. One OpenSky state-vector payload.
2. Current weather payloads for each configured airport.

The clients use a 20-second timeout and retry transient request/parse failures three times with exponential backoff. A single failed weather airport is logged and does not discard successful data from other airports.

### 2. Preserve raw data

Every successful response is written unchanged to the lake. Object keys are partitioned by source, entity, date, and hour:

```text
raw/source=opensky/entity=flight_states/dt=2026-09-06/hour=04/20260906T045350Z_<uuid>.json
raw/source=open_meteo/entity=weather_observation/dt=2026-09-06/hour=04/20260906T045350Z_<uuid>.json
```

This raw/bronze layer matters because it provides lineage, auditability, backfills, and the ability to replay an improved transformation without calling an external API again. The UUID prevents one collection from overwriting another.

### 3. Load and normalize

`Pipeline.load()` lists lake objects and routes each object by entity type.

The loader flattens OpenSky’s positional array into named columns and extracts current weather fields from Open-Meteo’s nested payload. It stores them in raw warehouse tables.

The `loaded_objects` ledger records the exact object key after a successful load. Before processing any object, the loader checks this ledger. This makes the process idempotent: a retry, restart, or rerun does not create duplicate rows for an already loaded raw object.

### 4. Transform with dbt

The dbt project creates a layered model:

| Model | What it does |
|---|---|
| `stg_flights` | Cleans callsigns, validates latitude/longitude ranges, renames columns, and converts velocity from m/s to km/h. |
| `stg_weather` | Standardizes weather fields, derives hourly time, and labels adverse weather. |
| `mart_weather_flight_impact` | Aggregates weather by airport/hour and joins hourly tracked-flight-state volume. |

Adverse weather is defined as precipitation above zero, wind at or above 30 km/h, or severe weather code values. The threshold is intentionally transparent SQL logic and should be calibrated with real historical delay data in a production use case.

dbt source tests validate key raw identifiers and required timestamps/airports. Additional tests can check accepted ranges, model freshness, and row-volume expectations.

### 5. Serve data

The FastAPI app is read-only and exposes:

| Endpoint | Purpose |
|---|---|
| `GET /v1/health` | Service health, timestamp, and active warehouse provider. |
| `GET /v1/flights/recent?limit=100` | Recent normalized flight state vectors. |
| `GET /v1/weather/latest?airport=KORD` | Latest observation for one airport or all configured airports. |
| `GET /v1/analytics/weather-impact?hours=24` | Hourly airport weather exposure and concurrent tracked-flight count. |
| `GET /docs` | Interactive OpenAPI/Swagger documentation. |

## Warehouse schema

### `raw_flight_states`

Grain: one aircraft state vector from one raw lake object.

Important columns: `event_id`, `object_key`, `observed_at`, `icao24`, `callsign`, `origin_country`, `latitude`, `longitude`, `baro_altitude`, `velocity`, `true_track`, and `on_ground`.

### `raw_weather_observations`

Grain: one airport weather observation from one raw lake object.

Important columns: `event_id`, `object_key`, `observed_at`, `airport`, `weather_time`, `temperature_c`, `precipitation_mm`, `weather_code`, `cloud_cover`, and `wind_speed_kph`.

### `loaded_objects`

Grain: one successfully processed raw lake object.

Important columns: `object_key` and `loaded_at`.

## Local versus cloud execution

### Local mode

The default is intentionally self-contained:

- Lake: `data/lake/`
- Warehouse: `data/warehouse/flight_weather.duckdb`
- dbt profile: DuckDB

This is ideal for development, portfolio demos, and automated tests. It needs no cloud account or paid service.

### AWS S3 lake

Set `LAKE_PROVIDER=s3`, `AWS_S3_BUCKET`, and `AWS_REGION`. The S3 adapter uses `boto3` and standard AWS credential resolution, so it works with local profiles, environment variables, IAM roles, or workload identity.

Terraform in `infra/aws/main.tf` provisions an S3 bucket with public access blocked, server-side encryption, and a lifecycle policy that transitions raw data to cheaper storage after 30 and 90 days.

### BigQuery warehouse

Set `WAREHOUSE_PROVIDER=bigquery`, `BIGQUERY_PROJECT`, and `BIGQUERY_DATASET`, then install the optional BigQuery dependencies. The BigQuery adapter creates partitioned raw tables, clusters flight records by aircraft identifier and weather records by airport, and uses the same object-ledger approach as DuckDB.

The included dbt profile is configured for local DuckDB. For a BigQuery deployment, create a separate protected dbt target using the project, dataset, service account/workload identity, and your organization’s deployment conventions.

## How to demo it live

From the repository directory:

```bash
cp .env.example .env
make install
flight-weather bootstrap-demo
make api
```

Then open `http://localhost:8000/docs`.

For a no-risk demo, `bootstrap-demo` writes deterministic, realistic synthetic records through the same lake and loader interfaces used by live collection. It demonstrates the whole system even when APIs are rate limited or unavailable.

To use live data once:

```bash
flight-weather pipeline --once
```

To run continuously every configured interval:

```bash
flight-weather pipeline
```

To validate code quality:

```bash
make test
make lint
make dbt-run
```

## Docker deployment model

Docker Compose runs two separately scalable services:

- `pipeline`: collection and loading process
- `api`: read-only FastAPI serving process

This separation is deliberate. A slow or failed data source should not bring down the query API, and API scaling should not multiply the number of collectors.

```bash
docker compose up --build
```

In a cloud environment, replace the long-running local collector with a scheduled job every five minutes (for example Cloud Run Jobs, ECS/Fargate scheduled tasks, Kubernetes CronJobs, or EventBridge-triggered compute). Keep the API as a separately deployed service.

## Reliability and data-engineering choices

### Idempotency

The object ledger is the central reliability feature. It prevents the most common failure mode in scheduled ingestion: duplicated warehouse records when a job retries after partial success.

### Raw data retention

Raw responses are not discarded after flattening. This allows backfills and improved transformation logic without depending on an external provider retaining old data.

### Partitioning

Lake keys include date and hour. This makes retention policies, incremental scanning, and future query engines such as Athena, Spark, or BigQuery external tables more efficient.

### Configuration and secrets

Pydantic Settings loads configuration from environment variables and `.env`. `.env` is ignored by Git. In production, use AWS Secrets Manager, GCP Secret Manager, or the workload platform’s native secrets mechanism.

### Observability

The application emits JSON-formatted logs and includes a collection run identifier. Useful production alerts would include:

- no successful flight source data in the expected interval;
- API error or rate-limit percentage;
- lake-object count versus warehouse-load count mismatch;
- data freshness for weather and flight tables;
- warehouse query latency and API error rate.

## Testing and CI

The project includes:

- a lake round-trip test;
- an end-to-end synthetic load/idempotency/API-data test;
- a FastAPI health endpoint test;
- Ruff linting;
- GitHub Actions CI that installs dependencies, lints, and runs pytest for pushes and pull requests.

The most valuable testing decision is testing the idempotency behavior, because it validates a core pipeline guarantee rather than only testing individual functions.

## Interview talking points

### Why did you use a lakehouse pattern?

I wanted the durability and replayability of a data lake while still providing fast structured analytics from a warehouse. The raw JSON layer protects me from schema changes and supports backfills. The warehouse and dbt layers make the data usable for APIs, BI, and analysts.

### Why store raw JSON before transforming it?

External APIs can change, requests can fail, and analytical requirements evolve. Storing the original payload means I can trace each warehouse row to a source object, replay the history with new logic, and avoid re-requesting data that may no longer be available.

### How do you prevent duplicates?

Every lake object gets a unique path. The loader maintains a `loaded_objects` ledger and checks it before flattening. The raw tables also use deterministic event IDs based on the lake object and row position. This gives safe retry behavior.

### Why DuckDB?

DuckDB provides analytical SQL with zero infrastructure, so the whole project can run on a laptop. The storage and warehouse layers are abstracted so the same ingestion flow can use S3 and BigQuery when cloud scale is needed.

### Why dbt instead of writing every transformation in Python?

dbt makes the analytical layer explicit, SQL-first, documented, testable, and lineage-aware. Python handles external I/O and orchestration well; dbt handles analytics transformations well. Separating those responsibilities improves maintainability.

### What would you improve for production scale?

I would use a workflow orchestrator such as Airflow, Dagster, or Prefect; write columnar Parquet rather than raw JSON-only lake objects; use managed secrets; provision IAM and warehouse infrastructure through Terraform; add distributed processing for higher volume; add data contracts/schema evolution checks; expose metrics through OpenTelemetry/Prometheus; and apply API authentication and rate limiting.

### How would you calculate real delay impact?

I would ingest scheduled and actual departure/arrival timestamps from an aviation schedule provider or BTS data. I would build a flight-leg fact table keyed by carrier, flight number, date, and route, calculate departure/arrival delay minutes, then join weather by airport and a time window around departure/arrival. A model could control for route, carrier, seasonality, hour, and airport congestion.

## Limitations to state honestly

- Flight records are state vectors, not complete commercial flight legs.
- Weather is collected only for a small configured airport set.
- The current analytical mart joins airport weather to overall hourly state-vector volume; it does not assign every aircraft to a particular airport.
- The local DBT profile targets DuckDB; a cloud deployment needs its own BigQuery dbt target and credentials.
- Anonymous OpenSky access is rate limited, so the synthetic demo command is provided for reliable presentations.

These are intentional scope boundaries for a portfolio project, not hidden caveats. Calling them out demonstrates strong data judgment.

## Resume-ready bullets

- Built an end-to-end real-time flight and weather lakehouse using Python, OpenSky, Open-Meteo, DuckDB, dbt, and FastAPI.
- Designed an idempotent ELT pipeline that stores immutable, partitioned JSON source records in a local/AWS S3 data lake and prevents duplicate warehouse loads through object-level ingestion tracking.
- Developed dbt staging and mart models to standardize real-time aircraft and airport-weather data and analyze adverse-weather flight exposure by hour.
- Delivered documented FastAPI analytics endpoints and a Dockerized two-service architecture separating scheduled ingestion from read-only data serving.
- Added infrastructure and engineering quality practices with Terraform S3 security/lifecycle policies, pytest, Ruff, environment-based secrets, structured logging, and GitHub Actions CI.

## Short closing statement for an interviewer

The strongest part of this project is that it is not just an API script. It demonstrates the full lifecycle of data: ingestion, raw retention, idempotent loading, warehouse modeling, transformation, serving, testing, cloud portability, and operational tradeoffs. I designed it so a recruiter can run it locally in minutes, while the architecture maps directly to a cloud production pipeline.
