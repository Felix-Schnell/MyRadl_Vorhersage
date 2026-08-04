"""Fetch MyRadl station master data (name, location, capacity) once and
write it to data/stations.csv. Re-run manually if the station network changes."""

import csv

import requests

from config import DATA_DIR, STATION_INFORMATION_URL

FIELDNAMES = ["station_id", "name", "lat", "lon", "capacity", "is_virtual_station"]


def fetch_stations() -> list[dict]:
    response = requests.get(STATION_INFORMATION_URL, timeout=30)
    response.raise_for_status()
    stations = response.json()["data"]["stations"]

    rows = []
    for station in stations:
        rows.append(
            {
                "station_id": station["station_id"],
                "name": station["name"],
                "lat": station["lat"],
                "lon": station["lon"],
                "capacity": station.get("capacity", ""),
                "is_virtual_station": station.get("is_virtual_station", ""),
            }
        )
    return rows


def write_stations_csv(rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out_path = DATA_DIR / "stations.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"{len(rows)} Stationen geschrieben nach {out_path}")


if __name__ == "__main__":
    write_stations_csv(fetch_stations())
