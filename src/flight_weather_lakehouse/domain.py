from dataclasses import dataclass


@dataclass(frozen=True)
class Airport:
    icao: str
    name: str
    latitude: float
    longitude: float


AIRPORTS = (
    Airport("KJFK", "John F. Kennedy International", 40.6413, -73.7781),
    Airport("KORD", "O'Hare International", 41.9742, -87.9073),
    Airport("KDFW", "Dallas Fort Worth International", 32.8998, -97.0403),
    Airport("KLAX", "Los Angeles International", 33.9416, -118.4085),
    Airport("KATL", "Hartsfield-Jackson Atlanta International", 33.6407, -84.4277),
)

