"""Trainiert ein grobes XGBoost-Modell: bikes_available pro Station, 1h in die Zukunft.

Nutzung:
    python model/train.py

Laedt die kompletten Daten aus dem `data`-Branch (git fetch + git show, kein lokaler
Checkout noetig), baut das stuendliche Feature-Panel und trainiert mit einem
zeitbasierten Train/Test-Split (letzter Tag = Test, Rest = Training) -- kein
zufaelliger Split, sonst leakt Information aus der Zukunft ins Training.

Als Referenz wird eine Persistenz-Baseline mitgerechnet ("in 1h ist es wie jetzt").
Nur wenn XGBoost die schlaegt, bringt das Feature Engineering ueberhaupt etwas.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error

from data import load_all
from features import FEATURE_COLUMNS, build_dataset

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"


def time_based_split(df: pd.DataFrame, test_hours: int = 24) -> tuple[pd.DataFrame, pd.DataFrame]:
    cutoff = df["timestamp"].max() - pd.Timedelta(hours=test_hours)
    train = df[df["timestamp"] <= cutoff]
    test = df[df["timestamp"] > cutoff]
    return train, test


def evaluate(y_true: pd.Series, y_pred: np.ndarray, label: str) -> dict:
    mae = mean_absolute_error(y_true, y_pred)
    rmse = mean_squared_error(y_true, y_pred) ** 0.5
    print(f"{label:>20s}  MAE={mae:.3f}  RMSE={rmse:.3f}")
    return {"mae": mae, "rmse": rmse}


def main() -> None:
    print("Lade Daten aus dem data-Branch ...")
    status, stations, weather = load_all()
    print(f"  {len(status):,} Status-Zeilen, {len(stations)} Stationen, {len(weather)} Wetter-Zeilen")

    print("Baue Feature-Panel (stuendlich resampled) ...")
    dataset = build_dataset(status, stations, weather)

    model_data = dataset.dropna(subset=[*FEATURE_COLUMNS, "target"]).copy()
    print(f"  {len(dataset):,} Panel-Zeilen, davon {len(model_data):,} nutzbar (nach dropna)")

    if len(model_data) < 200:
        print(
            "\nZu wenige nutzbare Zeilen fuer ein sinnvolles Training/Test-Split. "
            "Einfach spaeter mit mehr Daten aus dem data-Branch erneut ausfuehren."
        )
        return

    train_df, test_df = time_based_split(model_data)
    print(f"  Train: {len(train_df):,} Zeilen bis {train_df['timestamp'].max()}")
    print(f"  Test:  {len(test_df):,} Zeilen ab {test_df['timestamp'].min() if len(test_df) else '-'}")

    if len(test_df) == 0:
        print("\nKein Test-Zeitraum verfuegbar (Datenhistorie zu kurz). Abbruch.")
        return

    X_train, y_train = train_df[FEATURE_COLUMNS], train_df["target"]
    X_test, y_test = test_df[FEATURE_COLUMNS], test_df["target"]

    model = xgb.XGBRegressor(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        random_state=42,
    )
    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    pred = np.clip(pred, 0, None)

    print("\n--- Ergebnisse auf dem Test-Zeitraum ---")
    baseline_pred = test_df["lag_1h"]  # "in 1h wie jetzt" (Persistenz)
    evaluate(y_test, baseline_pred, "Baseline (Persistenz)")
    xgb_metrics = evaluate(y_test, pred, "XGBoost")

    print("\n--- Feature Importance (top 10) ---")
    importance = pd.Series(model.feature_importances_, index=FEATURE_COLUMNS).sort_values(
        ascending=False
    )
    print(importance.head(10).to_string())

    ARTIFACTS_DIR.mkdir(exist_ok=True)
    model.save_model(ARTIFACTS_DIR / "xgb_model.json")
    with open(ARTIFACTS_DIR / "metrics.json", "w") as f:
        json.dump(
            {
                "trained_at": pd.Timestamp.now("UTC").isoformat(),
                "train_rows": len(train_df),
                "test_rows": len(test_df),
                "test_period_start": str(test_df["timestamp"].min()),
                "test_period_end": str(test_df["timestamp"].max()),
                "xgboost": xgb_metrics,
                "feature_columns": FEATURE_COLUMNS,
            },
            f,
            indent=2,
        )
    print(f"\nModell gespeichert unter {ARTIFACTS_DIR / 'xgb_model.json'}")


if __name__ == "__main__":
    main()
