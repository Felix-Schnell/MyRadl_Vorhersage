"""Trainiert Multi-Horizont-Quantil-Modelle: bikes_available pro Station, 1-12h voraus.

Nutzung:
    python model/train.py

Laedt die kompletten Daten aus dem `data`-Branch (git fetch + git show, kein lokaler
Checkout noetig), baut das stuendliche Feature-Panel und trainiert pro Horizont (siehe
`features.HORIZONS`) ein XGBoost-Quantil-Modell, das gleichzeitig P10/P50/P90
vorhersagt (native Multi-Quantile-Regression, kein Ensemble noetig). Zwischen den
Horizonten wird spaeter im Frontend linear interpoliert, statt fuer jede einzelne
Stunde ein eigenes Modell zu trainieren -- bei 7 Tagen Historie wuerde das nur
Overfitting-Risiko erhoehen ohne echten Zusatznutzen.

Zeitbasierter Train/Test-Split (letzter Tag = Test, kein zufaelliger Split, sonst leakt
Information aus der Zukunft ins Training). Baseline zum Vergleich: der aktuell bekannte
Wert bleibt einfach so, wie er ist ("Persistenz").
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error

from data import load_all
from features import FEATURE_COLUMNS, HORIZONS, build_dataset

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
QUANTILES = [0.1, 0.5, 0.9]


def time_based_split(df: pd.DataFrame, test_hours: int = 24) -> tuple[pd.DataFrame, pd.DataFrame]:
    cutoff = df["timestamp"].max() - pd.Timedelta(hours=test_hours)
    train = df[df["timestamp"] <= cutoff]
    test = df[df["timestamp"] > cutoff]
    return train, test


def train_horizon(train_df: pd.DataFrame, test_df: pd.DataFrame, horizon: int) -> dict:
    target_col = f"target_h{horizon}"
    cols_needed = [*FEATURE_COLUMNS, target_col]
    train_h = train_df.dropna(subset=cols_needed)
    test_h = test_df.dropna(subset=cols_needed)

    if len(train_h) < 100 or len(test_h) == 0:
        print(f"  h={horizon:>2d}h  zu wenige Zeilen ({len(train_h)} train / {len(test_h)} test), uebersprungen")
        return {}

    X_train, y_train = train_h[FEATURE_COLUMNS], train_h[target_col]
    X_test, y_test = test_h[FEATURE_COLUMNS], test_h[target_col]

    model = xgb.XGBRegressor(
        objective="reg:quantileerror",
        quantile_alpha=QUANTILES,
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        random_state=42,
    )
    model.fit(X_train, y_train)
    pred = np.clip(model.predict(X_test), 0, None)  # Spalten: p10, p50, p90
    p10, p50, p90 = pred[:, 0], pred[:, 1], pred[:, 2]

    baseline_pred = test_h["bikes_available"]  # "in Xh wie jetzt gerade" (Persistenz)
    baseline_mae = mean_absolute_error(y_test, baseline_pred)
    model_mae = mean_absolute_error(y_test, p50)
    model_rmse = mean_squared_error(y_test, p50) ** 0.5
    coverage_80 = float(np.mean((y_test >= p10) & (y_test <= p90)))

    print(
        f"  h={horizon:>2d}h  n_test={len(test_h):>6d}  "
        f"MAE baseline={baseline_mae:.3f}  MAE p50={model_mae:.3f}  "
        f"RMSE p50={model_rmse:.3f}  80%-Intervall-Abdeckung={coverage_80:.1%}"
    )

    ARTIFACTS_DIR.mkdir(exist_ok=True)
    model.save_model(ARTIFACTS_DIR / f"xgb_h{horizon}.json")

    return {
        "horizon_hours": horizon,
        "train_rows": len(train_h),
        "test_rows": len(test_h),
        "baseline_mae": baseline_mae,
        "model_mae": model_mae,
        "model_rmse": model_rmse,
        "coverage_80pct": coverage_80,
    }


def main() -> None:
    print("Lade Daten aus dem data-Branch ...")
    status, stations, weather = load_all()
    print(f"  {len(status):,} Status-Zeilen, {len(stations)} Stationen, {len(weather)} Wetter-Zeilen")

    print("Baue Feature-Panel (stuendlich resampled) ...")
    dataset = build_dataset(status, stations, weather)
    print(f"  {len(dataset):,} Panel-Zeilen")

    train_df, test_df = time_based_split(dataset)
    print(f"  Train bis {train_df['timestamp'].max()}, Test ab {test_df['timestamp'].min()}")

    print(f"\nTrainiere je ein Quantil-Modell (P10/P50/P90) pro Horizont {HORIZONS} ...")
    results = [train_horizon(train_df, test_df, h) for h in HORIZONS]
    results = [r for r in results if r]

    ARTIFACTS_DIR.mkdir(exist_ok=True)
    with open(ARTIFACTS_DIR / "metrics.json", "w") as f:
        json.dump(
            {
                "trained_at": pd.Timestamp.now("UTC").isoformat(),
                "horizons": HORIZONS,
                "quantiles": QUANTILES,
                "feature_columns": FEATURE_COLUMNS,
                "results": results,
            },
            f,
            indent=2,
        )
    print(f"\nModelle + Metriken gespeichert unter {ARTIFACTS_DIR}")


if __name__ == "__main__":
    main()
