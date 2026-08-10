"""Feature Engineering: baut aus den rohen Polls ein stuendliches Panel pro Station.

Die Polls kommen unregelmaessig rein (siehe README/Analyse: 6-29 statt der
konfigurierten ~96 pro Tag). Statt mit festen Lags auf den rohen Timestamps zu
arbeiten, wird pro Station auf ein stuendliches Raster resampled (forward-fill des
letzten bekannten Zustands). Das macht Lag-Features und Trainings-/Test-Split ueber
Stationen hinweg vergleichbar.

Zielgroesse: `bikes_available` einer Station eine Stunde in der Zukunft.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Laenge einer Datenluecke, ab der ein forward-fill nicht mehr sinnvoll ist
# (Station vermutlich aus dem Feed verschwunden / laengerer Collector-Ausfall).
MAX_FFILL_GAP = pd.Timedelta(hours=6)

FORECAST_HORIZON = pd.Timedelta(hours=1)


def _hourly_panel_for_station(group: pd.DataFrame) -> pd.DataFrame:
    group = group.set_index("timestamp").sort_index()
    full_index = pd.date_range(group.index.min().floor("h"), group.index.max().ceil("h"), freq="1h")

    last_real_ts = group.index.to_series().reindex(full_index, method="ffill")
    minutes_since_poll = (full_index - last_real_ts).dt.total_seconds() / 60.0

    resampled = group.reindex(full_index, method="ffill")
    resampled["minutes_since_last_poll"] = minutes_since_poll
    # Zu alte forward-fills verwerfen statt mit veralteten Werten weiterzurechnen.
    stale = pd.to_timedelta(minutes_since_poll, unit="m") > MAX_FFILL_GAP
    resampled.loc[stale, ["bikes_available", "docks_available", "is_renting", "is_returning"]] = np.nan
    return resampled


def build_hourly_status(status: pd.DataFrame) -> pd.DataFrame:
    panels = []
    for station_id, group in status.groupby("station_id"):
        panel = _hourly_panel_for_station(group)
        panel["station_id"] = station_id
        panels.append(panel)
    hourly = pd.concat(panels).reset_index(names="timestamp")
    return hourly


def add_time_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    hour = df["timestamp"].dt.hour
    dow = df["timestamp"].dt.dayofweek
    df["hour"] = hour
    df["day_of_week"] = dow
    df["is_weekend"] = dow >= 5
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    df["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    df["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    return df


def add_weather_features(df: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    weather_cols = [
        "temperature_2m",
        "precipitation",
        "wind_speed_10m",
        "relative_humidity_2m",
        "weather_code",
    ]
    left = df.sort_values("timestamp")
    right = weather[["timestamp", *weather_cols]].sort_values("timestamp")
    merged = pd.merge_asof(
        left, right, on="timestamp", direction="nearest", tolerance=pd.Timedelta(hours=3)
    )
    return merged.sort_values(["station_id", "timestamp"]).reset_index(drop=True)


def add_station_features(df: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    station_cols = stations[["station_id", "lat", "lon", "capacity", "is_virtual_station"]].copy()
    station_cols["has_fixed_capacity"] = station_cols["capacity"].notna()
    station_cols["capacity"] = station_cols["capacity"].fillna(-1)
    return df.merge(station_cols, on="station_id", how="left")


def add_lag_and_target(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["station_id", "timestamp"]).copy()
    grouped = df.groupby("station_id")["bikes_available"]
    df["lag_1h"] = grouped.shift(1)
    df["lag_2h"] = grouped.shift(2)
    df["lag_3h"] = grouped.shift(3)
    df["rolling_mean_3h"] = grouped.shift(1).rolling(3).mean().reset_index(level=0, drop=True)
    df["target"] = grouped.shift(-1)
    return df


FEATURE_COLUMNS = [
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
    "is_weekend",
    "lat",
    "lon",
    "capacity",
    "has_fixed_capacity",
    "is_virtual_station",
    "lag_1h",
    "lag_2h",
    "lag_3h",
    "rolling_mean_3h",
    "minutes_since_last_poll",
    "temperature_2m",
    "precipitation",
    "wind_speed_10m",
    "relative_humidity_2m",
    "weather_code",
]


def build_dataset(
    status: pd.DataFrame, stations: pd.DataFrame, weather: pd.DataFrame
) -> pd.DataFrame:
    hourly = build_hourly_status(status)
    hourly = add_time_features(hourly)
    hourly = add_weather_features(hourly, weather)
    hourly = add_station_features(hourly, stations)
    hourly = add_lag_and_target(hourly)
    return hourly
