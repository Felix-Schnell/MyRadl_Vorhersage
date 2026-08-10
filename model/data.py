"""Laedt die gesammelten Daten aus dem `data`-Branch, ohne ihn lokal auszuchecken.

Der `data`-Branch enthaelt nur CSVs (station_status pro Tag, stations.csv, weather.csv)
und waechst laufend. Wir lesen ihn per `git show origin/data:<pfad>` direkt aus dem
Git-Objektspeicher, damit kein zweiter Working-Tree noetig ist und das Skript immer den
aktuellen Stand verwendet (nach einem `git fetch origin data`).
"""
from __future__ import annotations

import io
import subprocess
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_BRANCH = "origin/data"


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout


def _read_csv_from_branch(path: str) -> pd.DataFrame:
    content = _git("show", f"{DATA_BRANCH}:{path}")
    return pd.read_csv(io.StringIO(content))


def fetch_data_branch() -> None:
    subprocess.run(["git", "fetch", "origin", "data"], cwd=REPO_ROOT, check=True)


def list_status_files() -> list[str]:
    listing = _git("ls-tree", "-r", DATA_BRANCH, "--name-only")
    return sorted(
        name
        for name in listing.splitlines()
        if len(name) == len("YYYY-MM-DD.csv") and name.endswith(".csv") and name[:4].isdigit()
    )


def load_stations() -> pd.DataFrame:
    df = _read_csv_from_branch("stations.csv")
    df["is_virtual_station"] = df["is_virtual_station"].astype(bool)
    return df


def load_weather() -> pd.DataFrame:
    df = _read_csv_from_branch("weather.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


def load_status(max_days: int | None = None) -> pd.DataFrame:
    files = list_status_files()
    if max_days is not None:
        files = files[-max_days:]
    frames = [_read_csv_from_branch(f) for f in files]
    df = pd.concat(frames, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df["is_renting"] = df["is_renting"].astype(bool)
    df["is_returning"] = df["is_returning"].astype(bool)
    return df.sort_values(["station_id", "timestamp"]).reset_index(drop=True)


def load_all(max_days: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Gibt (status, stations, weather) zurueck. Ruft vorher `fetch_data_branch()` auf."""
    fetch_data_branch()
    return load_status(max_days=max_days), load_stations(), load_weather()
