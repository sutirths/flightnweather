import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import duckdb


class Warehouse(Protocol):
    def initialize(self) -> None: ...
    def is_loaded(self, object_key: str) -> bool: ...
    def load_flights(self, object_key: str, payload: dict[str, Any]) -> int: ...
    def load_weather(self, object_key: str, payload: dict[str, Any]) -> int: ...
    def recent_flights(self, limit: int) -> list[dict[str, Any]]: ...
    def latest_weather(self, airport: str | None) -> list[dict[str, Any]]: ...
    def weather_impact(self, hours: int) -> list[dict[str, Any]]: ...


class DuckDBWarehouse:
    def __init__(self, path: Path):
        self.path = path

    def _connection(self) -> duckdb.DuckDBPyConnection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(self.path))

    def initialize(self) -> None:
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS loaded_objects (
                    object_key VARCHAR PRIMARY KEY, loaded_at TIMESTAMPTZ NOT NULL
                );
                CREATE TABLE IF NOT EXISTS raw_flight_states (
                    event_id VARCHAR PRIMARY KEY, object_key VARCHAR NOT NULL, observed_at TIMESTAMPTZ,
                    icao24 VARCHAR, callsign VARCHAR, origin_country VARCHAR, time_position TIMESTAMPTZ,
                    longitude DOUBLE, latitude DOUBLE, baro_altitude DOUBLE, on_ground BOOLEAN,
                    velocity DOUBLE, true_track DOUBLE, vertical_rate DOUBLE, geo_altitude DOUBLE,
                    squawk VARCHAR, spi BOOLEAN, position_source INTEGER, loaded_at TIMESTAMPTZ NOT NULL
                );
                CREATE TABLE IF NOT EXISTS raw_weather_observations (
                    event_id VARCHAR PRIMARY KEY, object_key VARCHAR NOT NULL, observed_at TIMESTAMPTZ,
                    airport VARCHAR, weather_time TIMESTAMPTZ, latitude DOUBLE, longitude DOUBLE,
                    temperature_c DOUBLE, relative_humidity DOUBLE, precipitation_mm DOUBLE,
                    rain_mm DOUBLE, weather_code INTEGER, cloud_cover DOUBLE, wind_speed_kph DOUBLE,
                    wind_direction_degrees DOUBLE, loaded_at TIMESTAMPTZ NOT NULL
                );
            """)

    def is_loaded(self, object_key: str) -> bool:
        self.initialize()
        with self._connection() as conn:
            return conn.execute("SELECT 1 FROM loaded_objects WHERE object_key = ?", [object_key]).fetchone() is not None

    @staticmethod
    def _ts(value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=UTC)
        return datetime.fromisoformat(str(value))

    def load_flights(self, object_key: str, payload: dict[str, Any]) -> int:
        self.initialize()
        if self.is_loaded(object_key):
            return 0
        observed_at = self._ts(payload.get("time")) or datetime.now(UTC)
        rows = []
        for index, state in enumerate(payload.get("states") or []):
            event_id = hashlib.sha256(f"{object_key}:{index}".encode()).hexdigest()
            rows.append(
                [
                    event_id, object_key, observed_at, state[0], (state[1] or "").strip(), state[2],
                    self._ts(state[3]), state[5], state[6], state[7], state[8], state[9], state[10],
                    state[11], state[13], state[14], state[15], state[16], datetime.now(UTC),
                ]
            )
        with self._connection() as conn:
            conn.execute("BEGIN")
            try:
                if rows:
                    conn.executemany("""
                        INSERT OR IGNORE INTO raw_flight_states VALUES
                        (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, rows)
                conn.execute("INSERT INTO loaded_objects VALUES (?, ?)", [object_key, datetime.now(UTC)])
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return len(rows)

    def load_weather(self, object_key: str, payload: dict[str, Any]) -> int:
        self.initialize()
        if self.is_loaded(object_key):
            return 0
        current = payload.get("current") or {}
        row = [
            hashlib.sha256(object_key.encode()).hexdigest(), object_key,
            self._ts(payload.get("collected_at")) or datetime.now(UTC), payload.get("airport"),
            self._ts(current.get("time")), payload.get("latitude"), payload.get("longitude"),
            current.get("temperature_2m"), current.get("relative_humidity_2m"), current.get("precipitation"),
            current.get("rain"), current.get("weather_code"), current.get("cloud_cover"),
            current.get("wind_speed_10m"), current.get("wind_direction_10m"), datetime.now(UTC),
        ]
        with self._connection() as conn:
            conn.execute("BEGIN")
            try:
                conn.execute("INSERT OR IGNORE INTO raw_weather_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", row)
                conn.execute("INSERT INTO loaded_objects VALUES (?, ?)", [object_key, datetime.now(UTC)])
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return 1

    def _query(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        self.initialize()
        with self._connection() as conn:
            cursor = conn.execute(sql, params)
            columns = [item[0] for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def recent_flights(self, limit: int) -> list[dict[str, Any]]:
        return self._query("""
            SELECT icao24, callsign, origin_country, observed_at, longitude, latitude,
                   baro_altitude, velocity, on_ground
            FROM raw_flight_states ORDER BY observed_at DESC LIMIT ?
        """, [limit])

    def latest_weather(self, airport: str | None) -> list[dict[str, Any]]:
        return self._query("""
            WITH ranked AS (
                SELECT *, row_number() OVER (PARTITION BY airport ORDER BY observed_at DESC) AS rank
                FROM raw_weather_observations WHERE (? IS NULL OR airport = ?)
            ) SELECT airport, weather_time, observed_at, temperature_c, relative_humidity,
                     precipitation_mm, rain_mm, weather_code, cloud_cover, wind_speed_kph
              FROM ranked WHERE rank = 1 ORDER BY airport
        """, [airport, airport])

    def weather_impact(self, hours: int) -> list[dict[str, Any]]:
        # State vectors are associated to their closest configured airport by distance.
        return self._query("""
            WITH weather AS (
              SELECT airport, date_trunc('hour', observed_at) AS hour,
                     max(precipitation_mm) AS precipitation_mm, max(wind_speed_kph) AS wind_speed_kph,
                     max(cloud_cover) AS cloud_cover
              FROM raw_weather_observations
              WHERE observed_at >= now() - (? * INTERVAL 1 HOUR)
              GROUP BY 1,2
            ), flights AS (
              SELECT date_trunc('hour', observed_at) AS hour, count(*) AS tracked_flights
              FROM raw_flight_states WHERE observed_at >= now() - (? * INTERVAL 1 HOUR)
              GROUP BY 1
            )
            SELECT weather.airport, weather.hour, coalesce(flights.tracked_flights, 0) AS tracked_flights,
                   weather.precipitation_mm, weather.wind_speed_kph, weather.cloud_cover,
                   CASE WHEN weather.precipitation_mm > 0 OR weather.wind_speed_kph >= 30 THEN true ELSE false END AS adverse_weather
            FROM weather LEFT JOIN flights USING (hour) ORDER BY weather.hour DESC, weather.airport
        """, [hours, hours])


class BigQueryWarehouse:
    """BigQuery raw-zone adapter; dbt owns downstream analytical tables."""

    def __init__(self, project: str, dataset: str):
        try:
            from google.cloud import bigquery
        except ImportError as exc:
            raise RuntimeError("Install optional BigQuery dependencies: pip install -e '.[bigquery]'") from exc
        self.bigquery = bigquery
        self.client = bigquery.Client(project=project)
        self.project, self.dataset = project, dataset

    def initialize(self) -> None:
        self.client.create_dataset(self.bigquery.Dataset(f"{self.project}.{self.dataset}"), exists_ok=True)
        statements = [
            "CREATE TABLE IF NOT EXISTS `loaded_objects` (object_key STRING NOT NULL, loaded_at TIMESTAMP NOT NULL)",
            """CREATE TABLE IF NOT EXISTS `raw_flight_states` (
                event_id STRING NOT NULL, object_key STRING NOT NULL, observed_at TIMESTAMP, icao24 STRING,
                callsign STRING, origin_country STRING, time_position TIMESTAMP, longitude FLOAT64,
                latitude FLOAT64, baro_altitude FLOAT64, on_ground BOOL, velocity FLOAT64, true_track FLOAT64,
                vertical_rate FLOAT64, geo_altitude FLOAT64, squawk STRING, spi BOOL, position_source INT64,
                loaded_at TIMESTAMP NOT NULL) PARTITION BY DATE(observed_at) CLUSTER BY icao24""",
            """CREATE TABLE IF NOT EXISTS `raw_weather_observations` (
                event_id STRING NOT NULL, object_key STRING NOT NULL, observed_at TIMESTAMP, airport STRING,
                weather_time TIMESTAMP, latitude FLOAT64, longitude FLOAT64, temperature_c FLOAT64,
                relative_humidity FLOAT64, precipitation_mm FLOAT64, rain_mm FLOAT64, weather_code INT64,
                cloud_cover FLOAT64, wind_speed_kph FLOAT64, wind_direction_degrees FLOAT64,
                loaded_at TIMESTAMP NOT NULL) PARTITION BY DATE(observed_at) CLUSTER BY airport""",
        ]
        for statement in statements:
            self.client.query(statement, default_dataset=f"{self.project}.{self.dataset}").result()

    def _rows(self, sql: str, parameters: list[Any] | None = None) -> list[dict[str, Any]]:
        config = self.bigquery.QueryJobConfig(
            default_dataset=f"{self.project}.{self.dataset}",
            query_parameters=parameters or [],
        )
        return [dict(row.items()) for row in self.client.query(sql, job_config=config).result()]

    def is_loaded(self, object_key: str) -> bool:
        self.initialize()
        params = [self.bigquery.ScalarQueryParameter("object_key", "STRING", object_key)]
        return bool(self._rows("SELECT 1 FROM `loaded_objects` WHERE object_key = @object_key LIMIT 1", params))

    def load_flights(self, object_key: str, payload: dict[str, Any]) -> int:
        self.initialize()
        if self.is_loaded(object_key):
            return 0
        observed_at = DuckDBWarehouse._ts(payload.get("time")) or datetime.now(UTC)
        rows = []
        for index, state in enumerate(payload.get("states") or []):
            rows.append({
                "event_id": hashlib.sha256(f"{object_key}:{index}".encode()).hexdigest(), "object_key": object_key,
                "observed_at": observed_at.isoformat(), "icao24": state[0], "callsign": (state[1] or "").strip(),
                "origin_country": state[2], "time_position": self._iso(state[3]), "longitude": state[5], "latitude": state[6],
                "baro_altitude": state[7], "on_ground": state[8], "velocity": state[9], "true_track": state[10],
                "vertical_rate": state[11], "geo_altitude": state[13], "squawk": state[14], "spi": state[15],
                "position_source": state[16], "loaded_at": datetime.now(UTC).isoformat(),
            })
        errors = self.client.insert_rows_json(f"{self.project}.{self.dataset}.raw_flight_states", rows)
        if errors:
            raise RuntimeError(f"BigQuery flight insert failed: {errors}")
        self._mark_loaded(object_key)
        return len(rows)

    def load_weather(self, object_key: str, payload: dict[str, Any]) -> int:
        self.initialize()
        if self.is_loaded(object_key):
            return 0
        current = payload.get("current") or {}
        row = {
            "event_id": hashlib.sha256(object_key.encode()).hexdigest(), "object_key": object_key,
            "observed_at": self._iso(payload.get("collected_at")) or datetime.now(UTC).isoformat(),
            "airport": payload.get("airport"), "weather_time": self._iso(current.get("time")),
            "latitude": payload.get("latitude"), "longitude": payload.get("longitude"),
            "temperature_c": current.get("temperature_2m"), "relative_humidity": current.get("relative_humidity_2m"),
            "precipitation_mm": current.get("precipitation"), "rain_mm": current.get("rain"),
            "weather_code": current.get("weather_code"), "cloud_cover": current.get("cloud_cover"),
            "wind_speed_kph": current.get("wind_speed_10m"), "wind_direction_degrees": current.get("wind_direction_10m"),
            "loaded_at": datetime.now(UTC).isoformat(),
        }
        errors = self.client.insert_rows_json(f"{self.project}.{self.dataset}.raw_weather_observations", [row])
        if errors:
            raise RuntimeError(f"BigQuery weather insert failed: {errors}")
        self._mark_loaded(object_key)
        return 1

    @staticmethod
    def _iso(value: Any) -> str | None:
        parsed = DuckDBWarehouse._ts(value)
        return parsed.isoformat() if parsed else None

    def _mark_loaded(self, object_key: str) -> None:
        errors = self.client.insert_rows_json(
            f"{self.project}.{self.dataset}.loaded_objects",
            [{"object_key": object_key, "loaded_at": datetime.now(UTC).isoformat()}],
        )
        if errors:
            raise RuntimeError(f"BigQuery ledger insert failed: {errors}")

    def recent_flights(self, limit: int) -> list[dict[str, Any]]:
        return self._rows("""
            SELECT icao24, callsign, origin_country, observed_at, longitude, latitude, baro_altitude, velocity, on_ground
            FROM `raw_flight_states` ORDER BY observed_at DESC LIMIT @limit
        """, [self.bigquery.ScalarQueryParameter("limit", "INT64", limit)])

    def latest_weather(self, airport: str | None) -> list[dict[str, Any]]:
        return self._rows("""
            SELECT airport, weather_time, observed_at, temperature_c, relative_humidity, precipitation_mm,
                   rain_mm, weather_code, cloud_cover, wind_speed_kph
            FROM `raw_weather_observations`
            WHERE (@airport IS NULL OR airport = @airport)
            QUALIFY row_number() OVER (PARTITION BY airport ORDER BY observed_at DESC) = 1
            ORDER BY airport
        """, [self.bigquery.ScalarQueryParameter("airport", "STRING", airport)])

    def weather_impact(self, hours: int) -> list[dict[str, Any]]:
        return self._rows("""
            WITH weather AS (
              SELECT airport, TIMESTAMP_TRUNC(observed_at, HOUR) AS hour, max(precipitation_mm) AS precipitation_mm,
                     max(wind_speed_kph) AS wind_speed_kph, max(cloud_cover) AS cloud_cover
              FROM `raw_weather_observations` WHERE observed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR)
              GROUP BY 1, 2
            ), flights AS (
              SELECT TIMESTAMP_TRUNC(observed_at, HOUR) AS hour, count(*) AS tracked_flights
              FROM `raw_flight_states` WHERE observed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @hours HOUR) GROUP BY 1
            )
            SELECT weather.airport, weather.hour, IFNULL(flights.tracked_flights, 0) AS tracked_flights,
                   weather.precipitation_mm, weather.wind_speed_kph, weather.cloud_cover,
                   weather.precipitation_mm > 0 OR weather.wind_speed_kph >= 30 AS adverse_weather
            FROM weather LEFT JOIN flights USING (hour) ORDER BY hour DESC, airport
        """, [self.bigquery.ScalarQueryParameter("hours", "INT64", hours)])


def build_warehouse(provider: str, duckdb_path: Path, project: str | None, dataset: str) -> Warehouse:
    if provider == "bigquery":
        if not project:
            raise ValueError("BIGQUERY_PROJECT is required for WAREHOUSE_PROVIDER=bigquery")
        return BigQueryWarehouse(project, dataset)
    return DuckDBWarehouse(duckdb_path)
