# Status: Vorhersagemodell + Karte (Stand 2026-08-10, Session 2)

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
  Zufalls-Split, sonst Leakage aus der Zukunft). Trainiert **pro Horizont ein
  XGBoost-Quantil-Modell** (natives `reg:quantileerror` mit `quantile_alpha=[0.1,0.5,0.9]`,
  ein Modell liefert alle drei Quantile gleichzeitig). Horizonte: `features.HORIZONS =
  [1,2,3,4,6,8,10,12]` Stunden. Vergleich gegen Persistenz-Baseline ("bleibt wie
  jetzt"). Speichert Modelle als `model/artifacts/xgb_h<H>.json` + `metrics.json`
  (Ordner gitignored, wird bei jedem Lauf neu erzeugt).
- **`model/generate_predictions.py`** — lädt die trainierten Modelle, holt pro
  Station den aktuellen Stand (letzter echter Poll, nicht resampled) + die
  P10/P50/P90-Vorhersage je Horizont, schreibt `docs/data/predictions.json`
  (gitignored, wird von der Karte geladen).
- **`docs/index.html`** — statische Karte mit Leaflet (CDN), Slider 0–12h,
  Stationsfarbe nach Füllstand, Klick/Popup zeigt aktuellen Stand + Vorhersage +
  80%-Unsicherheitsband. Zwischen den trainierten Horizonten wird im Frontend linear
  interpoliert (kein Modell pro einzelner Stunde, siehe unten warum).
- **`.github/workflows/predict.yml`** — läuft stündlich (`25 * * * *`, versetzt zu
  Collector/Wetter-Workflows), trainiert neu, generiert `predictions.json`, kopiert
  `docs/` in einen separaten `gh-pages`-Branch (gleiches Worktree-Pattern wie
  `collect.yml`/`weather.yml` für den `data`-Branch) und pusht. **main bleibt damit
  weiterhin nur Code**, der `gh-pages`-Branch ist die deploybare Ausgabe.
- **`requirements-model.txt`** — zusätzliche ML-Abhängigkeiten (xgboost,
  scikit-learn), getrennt von `requirements.txt`, damit der Collector (läuft auch in
  GitHub Actions) schlank bleibt.
- **`.claude/launch.json`** — lokaler Static-Server (`python -m http.server` auf
  `docs/`) zum Testen der Karte im Browser ohne GitHub Pages.

### Warum Multi-Horizont mit nur 8 Ankerpunkten statt 12 Einzelmodellen?

Bei 7 Tagen Historie bringt ein eigenes Modell pro Stunde (1,2,...,12) keinen
Erkenntnisgewinn gegenüber Interpolation zwischen wenigen Ankern, erhöht aber
Trainingszeit und Overfitting-Risiko. Mit wachsendem `data`-Branch kann man die Liste
in `features.HORIZONS` einfach verfeinern.

### Warum Quantile statt einer einzelnen Zahl?

Der Nutzer wollte eine "Wahrscheinlichkeit" zum Wert sehen. Eine einzelne Prozentzahl
wäre bei 7 Tagen Daten Scheingenauigkeit. Stattdessen: P10/P50/P90 als ehrliches
80%-Unsicherheitsband, das mit wachsender Datenmenge automatisch enger wird.

## Wichtige Korrektur gegenüber Session 1

Die alte Persistenz-Baseline in `train.py` hat fälschlich `lag_1h` (Wert von vor 1h)
mit dem 1h-Ziel verglichen, statt dem aktuellen Wert `bikes_available` zum
Vorhersagezeitpunkt. Das ist jetzt korrigiert (`train_horizon()` nutzt
`test_h["bikes_available"]` als Baseline). Dadurch sind die Zahlen aus Session 1
(MAE 0.631 Baseline) **nicht direkt vergleichbar** mit den neuen, korrekteren Zahlen
unten.

## Letztes Trainingsergebnis (mit ~7 Tagen Daten, Stand 2026-08-10)

```
h= 1h  MAE baseline=0.349  MAE p50=0.657  RMSE p50=1.443  80%-Abdeckung=84.1%
h= 2h  MAE baseline=0.592  MAE p50=0.855  RMSE p50=1.770  80%-Abdeckung=83.0%
h= 3h  MAE baseline=0.778  MAE p50=1.010  RMSE p50=2.049  80%-Abdeckung=81.7%
h= 4h  MAE baseline=0.935  MAE p50=1.136  RMSE p50=2.200  80%-Abdeckung=81.2%
h= 6h  MAE baseline=1.184  MAE p50=1.342  RMSE p50=2.437  80%-Abdeckung=80.0%
h= 8h  MAE baseline=1.389  MAE p50=1.494  RMSE p50=2.618  80%-Abdeckung=79.5%
h=10h  MAE baseline=1.561  MAE p50=1.621  RMSE p50=2.787  80%-Abdeckung=78.2%
h=12h  MAE baseline=1.704  MAE p50=1.723  RMSE p50=2.915  80%-Abdeckung=78.9%
```

**Die Persistenz-Baseline schlägt XGBoost bei jedem Horizont.** Das ist konsistent mit
Session 1: 7 Tage reichen noch nicht, damit Zeit-/Wetter-Features etwas beitragen, was
"aktueller Wert bleibt ungefähr gleich" nicht auch könnte. Die 80%-Intervall-Abdeckung
liegt aber gut bei ~80% (gute Kalibrierung der Quantile trotz wenig Daten) — die
Unsicherheitsbänder sind also ehrlich, auch wenn der Mittelwert (P50) noch nicht
besser als naiv ist.

**Konsequenz:** Die Karte ist aktuell primär ein funktionierender Demo-Prototyp für
UI/Pipeline, aber die Vorhersagequalität ist noch nicht besser als "schau auf den
aktuellen Stand". Sollte man klar kommunizieren, falls die Karte geteilt wird.

## Wie man weitermacht

```bash
git pull
pip install -r requirements-model.txt
python model/train.py
python model/generate_predictions.py
python -m http.server 8000 --directory docs   # lokal testen
```

Lädt automatisch den aktuellen `data`-Branch, kein manueller Sync nötig.

## GitHub Pages — noch nicht aktiviert!

Der Plan war, dass Claude GitHub Pages automatisch aktiviert (Source: `gh-pages`-
Branch), aber die lokale Umgebung hatte **kein `gh` CLI installiert**, daher konnte
das nicht automatisiert werden. Zwei offene Schritte, bevor die Karte online ist:

1. `.github/workflows/predict.yml` muss mindestens einmal laufen (automatisch stündlich,
   oder manuell über GitHub → Actions → "Update prediction map" → "Run workflow"),
   damit der `gh-pages`-Branch überhaupt existiert.
2. Im Repo unter **Settings → Pages → Source** auf "Deploy from a branch" stellen,
   Branch `gh-pages`, Ordner `/ (root)`. Danach ist die Karte unter
   `https://felix-schnell.github.io/MyRadl_Vorhersage/` erreichbar (kann ein paar
   Minuten dauern).

## Offene Punkte / nächste Schritte

- **GitHub Pages aktivieren** (siehe oben) — das Wichtigste, damit die Karte
  überhaupt erreichbar ist.
- **Einfach neu trainieren, sobald mehr Daten da sind** — die Pipeline läuft eh
  stündlich automatisch neu (`predict.yml`), sollte also von selbst besser werden.
  Sinnvoll wäre ein bewusster Check nach 2–3 Wochen, wenn mindestens ein voller
  Wochenzyklus vorliegt, ob die Baseline endlich geschlagen wird.
- **Trainingszeit im Auge behalten** — `predict.yml` trainiert bei jedem Lauf (stündlich)
  alle 8 Horizont-Modelle komplett neu. Das skaliert nicht ewig; wenn der `data`-Branch
  deutlich wächst, Training und Predictions-Generierung entkoppeln (z.B. Training nur
  täglich, Predictions stündlich mit dem zuletzt trainierten, committeten Modell).
- **Metriken pro Station statt nur global** — aktuell wird MAE/RMSE über alle
  Stationen gemittelt berichtet. Aufschlüsselung nach Stationstyp (fest/virtuell,
  viel/wenig Verkehr) wäre informativ.
- **Hyperparameter-Tuning** — aktuell feste, ungetunte XGBoost-Parameter.
- **Stationsspezifische Historie als Feature** (z.B. mittlere Auslastung je Station/
  Stunde) — macht bei 7 Tagen noch keinen Sinn (zu wenig Wiederholungen), später
  nachrüstbar.
- **`docks_available` ist weiterhin komplett ungenutzt** (nur 10/786 Stationen mit
  fester Kapazität) — bewusste Entscheidung, kein offener Punkt.
- Karte hat aktuell keinerlei Caching/Performance-Optimierung für die
  `predictions.json` (~470 KB bei 786 Stationen) — für den Prototyp okay, bei viel
  mehr Stationen oder Horizonten ggf. Kompression/Pagination nötig.
