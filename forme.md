for me: 
---

Project explanation
This is a production-style data engineering project that simulates how an airline, logistics company, or travel platform could collect and analyze real-time operational data.
It ingests two live data sources:
- Flight-position data from the OpenSky Network API
- Weather conditions from the Open-Meteo API
The pipeline works like this:
Flight + weather APIs
        ↓
Raw JSON data lake (local files or AWS S3)
        ↓
Flattened warehouse tables (DuckDB locally or BigQuery)
        ↓
dbt transformations and analytics marts
        ↓
FastAPI endpoints for serving results
Every time the pipeline runs, it pulls current flight state vectors and weather observations for major airports such as O’Hare, JFK, LAX, Atlanta, and Dallas-Fort Worth.
The original API responses are saved as immutable JSON files in a partitioned data lake structure. For example, files are organized by source, entity type, date, and hour. This is important because raw data can be replayed or reprocessed later without re-calling the external APIs.
The loader then flattens the JSON into warehouse tables:
- raw_flight_states stores aircraft identifier, callsign, position, altitude, speed, heading, and whether the plane is on the ground.
- raw_weather_observations stores airport weather, including temperature, precipitation, wind speed, cloud coverage, and weather code.
- loaded_objects tracks every processed lake object so rerunning the pipeline does not create duplicate records.
dbt creates cleaner analytical models on top of the raw warehouse data. The main mart, mart_weather_flight_impact, combines hourly weather conditions with flight activity to identify periods of adverse-weather exposure.
Finally, FastAPI exposes the warehouse data through documented REST endpoints. A user can retrieve recent aircraft, the latest airport weather, and weather-impact analytics through /docs or normal API calls.
One important modeling detail: OpenSky provides flight positions, not commercial scheduled arrival and departure delays. Therefore, the project correctly analyzes weather-related flight exposure rather than falsely claiming it calculates true airline delay. In a production version, you could add Aviationstack, Bureau of Transportation Statistics, or an airline schedule feed to calculate actual delay impact.
Resume bullet points
- Built a real-time flight and weather data lakehouse pipeline using Python, OpenSky Network, and Open-Meteo REST APIs.
- Designed a lakehouse architecture that ingests API data into partitioned raw JSON storage, supports local storage and AWS S3, and loads normalized records into DuckDB or Google BigQuery.
- Implemented idempotent ETL loading with object-level ingestion tracking to prevent duplicate flight and weather records during retries or scheduled runs.
- Developed dbt staging models and analytical marts to measure adverse-weather exposure across airport weather observations and real-time flight activity.
- Created a FastAPI analytics service with documented REST endpoints for flight states, latest weather observations, health checks, and weather-impact metrics.
- Containerized the platform with Docker Compose and added automated testing, Ruff linting, GitHub Actions CI, Terraform-based S3 infrastructure, and environment-based configuration.
- Applied production data engineering practices including raw-data retention, partitioned lake storage, retry logic, timeouts, structured logging, cloud configuration, and secret-safe environment variables.
Technologies
Python, FastAPI, REST APIs, OpenSky Network API, Open-Meteo API, DuckDB, Google BigQuery, AWS S3, dbt, Docker, Docker Compose, Terraform, pytest, Ruff, GitHub Actions, SQL, JSON, Pydantic, boto3.


----
Here is how the system works from start to finish, step by step:

Step 1: Getting the Live Data (APIs)
Every time the pipeline runs, a Python script reaches out to two free online sources:

OpenSky Network: Gives live flight positions (plane ID, latitude, longitude, altitude, speed).

Open-Meteo: Gives live weather observations for major airports like LAX, JFK, and DFW (temperature, rain, wind speed, cloud cover).

Step 2: Saving the "Fossil Record" (Data Lake & S3)
Before changing or processing the data, the raw API responses are saved as JSON files in AWS S3 (or local folders).

Organized Folders: Files are stored in partitioned folders by date and hour (e.g., year=2026/month=09/day=06/hour=12/).

Why this matters for interviews: Storing raw data as "immutable" (unchanging) files ensures that if a database crashes or your code changes later, you can reprocess past data without losing anything or re-calling external APIs.

Step 3: Flattening into Tables & Preventing Duplicates (Warehouse & Idempotency)
A loader script reads the raw JSON files, un-nests them into clean database tables (using DuckDB locally or Google BigQuery in the cloud):

raw_flight_states: Stores aircraft coordinates, speed, and callsign.

raw_weather_observations: Stores airport temperatures, precipitation, and weather codes.

loaded_objects: A tracking log that acts like a guest list. Before loading a file, the system checks this table. If a file was already loaded, it skips it.

Why this matters for interviews: This makes the pipeline idempotent—meaning you can run it 10 times in a row, and it will never insert duplicate records into your database.

Step 4: Cleaning & Combining the Data (dbt)
Raw data is messy. You use dbt (Data Build Tool) to run automated SQL transformations that clean the tables and join them together.

The Analytics Mart (mart_weather_flight_impact): This final table combines plane locations with nearby airport weather to calculate adverse-weather exposure—identifying which flights are flying through storms or heavy winds.

Important detail: The system measures weather exposure, not official airline delays, because OpenSky tracks plane positions rather than official airline flight schedules.

Step 5: Delivering Results (FastAPI)
Instead of forcing users to write SQL queries directly against the database, you put a FastAPI web server on top of it.

A user or web app sends an HTTP request to an endpoint like /weather or /impact.

FastAPI queries the database and sends back clean JSON responses instantly.

Step 6: Packaging & Automation (Docker, Terraform, CI/CD)
To make this run reliably like production software:

Docker / Docker Compose: Packages the whole app (Python, DuckDB, FastAPI) into isolated containers so it runs identically on any computer.

Terraform: Infrastructure-as-Code that automatically provisions your AWS S3 bucket instead of requiring manual setup in the AWS console.

GitHub Actions: Runs automated unit tests (pytest) and code linter checks (Ruff) every time you push new code.

How to summarize it in 30 seconds during an interview:
"My project ingests live flight coordinates and airport weather data from REST APIs into a partitioned raw JSON data lake on AWS S3. I built an idempotent loader that flattens this data into BigQuery/DuckDB without duplicate records, and used dbt to model weather exposure on active flights. Finally, I exposed those analytical metrics via a containerized FastAPI microservice deployed with Docker, Terraform, and GitHub Actions CI/CD."
