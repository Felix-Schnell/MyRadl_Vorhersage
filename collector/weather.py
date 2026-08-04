"""Fetch current weather for the MyRadl service region (Open-Meteo, kein API-Key noetig)
und haenge eine Zeile an data/weather.csv an. Gedacht fuer stuendlichen Aufruf -- Wetter
aendert sich viel langsamer als die Stationsbelegung, ein Wert pro Region reicht.

Der Abfragepunkt ist der geografische Schwerpunkt aller MyRadl-Stationen (aus stations.csv
berechnet, falls vorhanden), nicht ein einzelner Stadtpunkt -- deckt damit die Region ab,
in der die Stationen tatsaechlich liegen.
"""

import csv
import logging
import sys
import time
from datetime import datetime, timezone

import requests

from config import (
    DATA_DIR,
    FALLBACK_LAT,
    FALLBACK_LON,
    WEATHER_API_URL,
    WEATHER_INTERVAL_SECONDS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("myradl-weather")

FIELDNAMES = [
    "timestamp",
    "latitude",
    "longitude",
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "relative_humidity_2m",
    "weather_code",
]


def region_centroid() -> tuple[float, float]:
    stations_path = DATA_DIR / "stations.csv"
    if not stations_path.exists():
        logger.warning("stations.csv nicht gefunden, nutze Fallback-Koordinaten")
        return FALLBACK_LAT, FALLBACK_LON

    lats, lons = [], []
    with open(stations_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lats.append(float(row["lat"]))
            lons.append(float(row["lon"]))

    if not lats:
        return FALLBACK_LAT, FALLBACK_LON
    return sum(lats) / len(lats), sum(lons) / len(lons)


def fetch_weather(lat: float, lon: float) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,precipitation,weather_code,wind_speed_10m,relative_humidity_2m",
        "timezone": "UTC",
    }
    response = requests.get(WEATHER_API_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()["current"]


def append_row(current: dict, lat: float, lon: float, now: datetime) -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "weather.csv"
    file_exists = out_path.exists()

    row = {
        "timestamp": now.isoformat(),
        "latitude": lat,
        "longitude": lon,
        "temperature_2m": current.get("temperature_2m", ""),
        "precipitation": current.get("precipitation", ""),
        "wind_speed_10m": current.get("wind_speed_10m", ""),
        "relative_humidity_2m": current.get("relative_humidity_2m", ""),
        "weather_code": current.get("weather_code", ""),
    }

    with open(out_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    return str(out_path)


def poll_once() -> None:
    now = datetime.now(timezone.utc)
    lat, lon = region_centroid()
    current = fetch_weather(lat, lon)
    out_path = append_row(current, lat, lon, now)
    logger.info("Wetter geschrieben nach %s: %s", out_path, current)


def run_forever() -> None:
    logger.info(
        "MyRadl-Wetter-Collector gestartet, Intervall=%ds, Datenordner=%s",
        WEATHER_INTERVAL_SECONDS,
        DATA_DIR,
    )
    while True:
        try:
            poll_once()
        except Exception:
            logger.exception("Wetter-Abruf fehlgeschlagen, versuche es im naechsten Intervall erneut")
        time.sleep(WEATHER_INTERVAL_SECONDS)


if __name__ == "__main__":
    if "--once" in sys.argv:
        poll_once()
    else:
        try:
            run_forever()
        except KeyboardInterrupt:
            logger.info("Wetter-Collector gestoppt (Ctrl+C)")
