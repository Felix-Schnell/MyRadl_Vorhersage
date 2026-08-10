# Status: Vorhersagemodell (Stand 2026-08-10)

Diese Datei ist der Übergabepunkt für eine Fortsetzung auf einem anderen Rechner /
in einem anderen Chat. Sie fasst zusammen, was gebaut wurde, warum genau so, und was
als Nächstes sinnvoll ist.

## Ausgangslage

Der Collector sammelt seit 2026-08-04 Live-Verfügbarkeitsdaten (siehe Haupt-
[README.md](../README.md)). Zum Zeitpunkt dieser Session lagen ca. 7 Tage Daten vor
(786 Stationen, `data`-Branch). Das ist zu wenig für ein belastbares Modell (kein
voller Wochenzyklus, keine Saisonalität), aber genug, um Feature-Engineering- und
Trainings-Pipeline aufzubauen und als Prototyp durchzurechnen — mit dem Plan, die
Pipeline einfach mit wachsendem `data`-Branch erneut laufen zu lassen.

## Zwei wichtige Erkenntnisse aus der Datenanalyse

1. **Nur 10 von 786 Stationen haben eine feste `capacity`.** Der Rest sind virtuelle
   Rückgabezonen ohne feste Kapazität. `docks_available` ist dadurch praktisch immer 0
   und als Feature nutzlos.
2. **Das Polling ist viel unregelmäßiger als konfiguriert.** Cron steht auf alle
   15 Minuten, real kommen aber nur 6–29 Polls/Tag an (GitHub Actions throttelt
   Scheduled Workflows bei public Repos stark), mit Lücken von 30 Minuten bis über
   2 Stunden. Deshalb arbeitet die Pipeline nicht mit festen Lags auf den rohen
   Timestamps, sondern resampled pro Station auf ein **stündliches Raster**
   (forward-fill des letzten bekannten Zustands, siehe `MAX_FFILL_GAP` in
   `features.py` — bei Lücken über 6h wird nicht mehr geffillt).

## Was gebaut wurde

- **`model/data.py`** — lädt Status-, Stations- und Wetterdaten direkt aus dem
  `data`-Branch per `git fetch` + `git show origin/data:<pfad>`, ohne den Branch
  lokal auszuchecken. Läuft also auf jedem Rechner mit Zugriff aufs Repo, ohne
  vorher `data/` manuell zu synchronisieren.
- **`model/features.py`** — Feature Engineering:
  - stündliches Panel pro Station (`build_hourly_status`)
  - Zeit-Features: Stunde/Wochentag als sin/cos, `is_weekend`
  - Wetter-Join per `merge_asof` (nächstgelegener Wert, Toleranz 3h)
  - Stations-Features: `lat`, `lon`, `capacity` (fehlend → -1), `has_fixed_capacity`,
    `is_virtual_station`
  - Lag-Features: `lag_1h`, `lag_2h`, `lag_3h`, `rolling_mean_3h`
  - Ziel: `target` = `bikes_available` der Station **1 Stunde in der Zukunft**
- **`model/train.py`** — zeitbasierter Train/Test-Split (letzte 24h = Test, kein
  Zufalls-Split, sonst Leakage aus der Zukunft), trainiert `XGBRegressor`, vergleicht
  gegen eine Persistenz-Baseline ("in 1h wie jetzt" = `lag_1h`), speichert Modell +
  Metriken unter `model/artifacts/` (gitignored).
- **`requirements-model.txt`** — zusätzliche ML-Abhängigkeiten (xgboost,
  scikit-learn), getrennt von `requirements.txt`, damit der Collector (läuft auch in
  GitHub Actions) schlank bleibt.

## Letztes Trainingsergebnis (mit ~7 Tagen Daten, Stand 2026-08-10)

```
Baseline (Persistenz)  MAE=0.631  RMSE=1.478
XGBoost                MAE=0.742  RMSE=1.447
```

XGBoost schlägt die Baseline bei MAE noch nicht, bei RMSE minimal. Feature Importance:
`lag_1h` (~64%) und `rolling_mean_3h` (~25%) dominieren, Zeit-/Wetter-Features tragen
kaum bei. Das ist bei einer Woche Historie ohne vollen Wochenzyklus erwartbar — **kein
Bug**, sondern der zu erwartende Zustand bei dieser Datenmenge.

## Wie man weitermacht

```bash
git pull
pip install -r requirements-model.txt
python model/train.py
```

Lädt automatisch den aktuellen `data`-Branch, kein manueller Sync nötig.

## Offene Punkte / nächste Schritte

- **Einfach neu trainieren, sobald mehr Daten da sind** (Hauptaufgabe — die Pipeline
  ist dafür ausgelegt). Sinnvoll wäre ein erneuter Check nach 2–3 Wochen, wenn
  mindestens ein voller Wochenzyklus vorliegt.
- **Andere Vorhersage-Horizonte testen** (z.B. 2h, 4h statt nur 1h) — aktuell ist der
  Horizont mit `FORECAST_HORIZON` in `features.py` hart auf 1h ausgelegt (wird aber
  aktuell noch nicht parametrisiert genutzt, nur als Dokumentation der Annahme).
- **Metriken pro Station statt nur global** — aktuell wird ein globales MAE/RMSE über
  alle Stationen berichtet. Sinnvoll wäre eine Aufschlüsselung, ob z.B. Stationen mit
  fester Kapazität oder mit viel Verkehr besser/schlechter vorhergesagt werden.
- **Hyperparameter-Tuning** — aktuell feste, ungetunte XGBoost-Parameter in
  `train.py` (`n_estimators=300`, `max_depth=5`, etc.), war für den Prototyp nicht
  nötig.
- **Stationsspezifische Historie als Feature** (z.B. mittlere Auslastung je Station/
  Stunde) — aktuell nicht enthalten, könnte mit mehr Daten helfen, macht bei 7 Tagen
  aber noch keinen Sinn (zu wenig Wiederholungen pro Station/Stunde-Kombination).
- **`docks_available` ist aktuell komplett ungenutzt** (siehe Erkenntnis oben) — kein
  offener Punkt, sondern bewusste Entscheidung, aber gut zu wissen falls jemand fragt
  warum das Feature fehlt.
- Kein Deployment/Serving-Code vorhanden — bisher nur Trainings-/Evaluations-Skript.
