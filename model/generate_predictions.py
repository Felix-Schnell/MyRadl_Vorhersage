"""Baut die predictions.json fuer die Karte: aktueller Stand + P10/P50/P90-Vorhersage
pro Station und trainiertem Horizont (siehe features.HORIZONS).

Nutzung:
    python model/generate_predictions.py

Braucht bereits trainierte Modelle unter model/artifacts/xgb_h<H>.json (siehe train.py).
Schreibt nach docs/data/predictions.json (wird von docs/index.html geladen).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

from data import load_all
from features import FEATURE_COLUMNS, HORIZONS, build_dataset

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "docs" / "data" / "predictions.json"
QUANTILE_LABELS = ["p10", "p50", "p90"]


def load_models() -> dict[int, xgb.XGBRegressor]:
    models = {}
    for h in HORIZONS:
        path = ARTIFACTS_DIR / f"xgb_h{h}.json"
        if not path.exists():
            print(f"  Warnung: kein Modell fuer Horizont {h}h unter {path}, wird uebersprungen")
            continue
        model = xgb.XGBRegressor()
        model.load_model(path)
        models[h] = model
    return models


def main() -> None:
    print("Lade Daten aus dem data-Branch ...")
    status, stations, weather = load_all()

    print("Baue Feature-Panel ...")
    dataset = build_dataset(status, stations, weather)
    latest = dataset.sort_values("timestamp").groupby("station_id").tail(1).set_index("station_id")

    current = (
        status.sort_values("timestamp")
        .groupby("station_id")
        .tail(1)
        .set_index("station_id")[["timestamp", "bikes_available"]]
    )

    print("Lade Modelle ...")
    models = load_models()
    if not models:
        raise SystemExit("Keine trainierten Modelle gefunden. Erst 'python model/train.py' ausfuehren.")

    print("Erzeuge Vorhersagen ...")
    station_rows = []
    for station_id, station_meta in stations.set_index("station_id").iterrows():
        entry = {
            "station_id": int(station_id),
            "name": station_meta["name"],
            "lat": float(station_meta["lat"]),
            "lon": float(station_meta["lon"]),
            "capacity": None if pd.isna(station_meta["capacity"]) else int(station_meta["capacity"]),
            "is_virtual_station": bool(station_meta["is_virtual_station"]),
        }

        if station_id in current.index:
            row = current.loc[station_id]
            entry["current"] = {
                "bikes_available": int(row["bikes_available"]),
                "timestamp": row["timestamp"].isoformat(),
            }
        else:
            entry["current"] = None

        forecast = {}
        if station_id in latest.index:
            feat_row = latest.loc[station_id, FEATURE_COLUMNS]
            if not feat_row.isna().any():
                X = feat_row.to_frame().T.astype(float)
                for h, model in models.items():
                    pred = np.clip(model.predict(X)[0], 0, None)
                    forecast[str(h)] = {
                        label: round(float(val), 2) for label, val in zip(QUANTILE_LABELS, pred)
                    }
        entry["forecast"] = forecast
        station_rows.append(entry)

    output = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "horizons": HORIZONS,
        "stations": station_rows,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)

    n_with_forecast = sum(1 for s in station_rows if s["forecast"])
    print(f"{len(station_rows)} Stationen, {n_with_forecast} mit Vorhersage -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
