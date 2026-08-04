"""Poll MyRadl station_status.json every 10 minutes and append one row per
station to data/YYYY-MM-DD.csv (UTC date). Runs until stopped with Ctrl+C.

nextbike bittet ausdruecklich darum, station_status.json nicht oefter als
alle 10 Minuten abzufragen -- POLL_INTERVAL_SECONDS deshalb nicht verkleinern.
"""

import csv
import logging
import sys
import time
from datetime import datetime, timezone

import requests

from config import DATA_DIR, POLL_INTERVAL_SECONDS, STATION_STATUS_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("myradl-poll")

FIELDNAMES = [
    "station_id",
    "timestamp",
    "bikes_available",
    "docks_available",
    "is_renting",
    "is_returning",
]


def fetch_station_status() -> list[dict]:
    response = requests.get(STATION_STATUS_URL, timeout=30)
    response.raise_for_status()
    return response.json()["data"]["stations"]


def append_rows(stations: list[dict], now: datetime) -> tuple[int, str]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / f"{now.strftime('%Y-%m-%d')}.csv"
    file_exists = out_path.exists()

    timestamp = now.isoformat()
    rows = [
        {
            "station_id": s["station_id"],
            "timestamp": timestamp,
            "bikes_available": s.get("num_bikes_available", ""),
            "docks_available": s.get("num_docks_available", ""),
            "is_renting": s.get("is_renting", ""),
            "is_returning": s.get("is_returning", ""),
        }
        for s in stations
    ]

    with open(out_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

    return len(rows), str(out_path)


def poll_once() -> None:
    now = datetime.now(timezone.utc)
    stations = fetch_station_status()
    count, out_path = append_rows(stations, now)
    logger.info("%d Stationen geschrieben nach %s", count, out_path)


def run_forever() -> None:
    logger.info(
        "MyRadl-Collector gestartet, Intervall=%ds, Datenordner=%s",
        POLL_INTERVAL_SECONDS,
        DATA_DIR,
    )
    while True:
        try:
            poll_once()
        except Exception:
            logger.exception("Poll fehlgeschlagen, versuche es im naechsten Intervall erneut")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    if "--once" in sys.argv:
        # Einmaliger Lauf fuer z.B. GitHub Actions, wo der Scheduler extern (Cron) sitzt.
        poll_once()
    else:
        try:
            run_forever()
        except KeyboardInterrupt:
            logger.info("Collector gestoppt (Ctrl+C)")
