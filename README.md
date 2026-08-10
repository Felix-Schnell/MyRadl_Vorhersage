# MyRadl Vorhersage

Sammelt Live-Verfügbarkeitsdaten von [MyRadl](https://myradl.de) (Bikesharing München,
Betreiber nextbike im Auftrag von MVV/MVG) über die öffentliche GBFS-Schnittstelle. Dies ist
aktuell **nur der Daten-Fetching-Teil** — noch kein Vorhersagemodell.

## GBFS-Endpunkt

MyRadl läuft unter der nextbike-Domain `ml`. GBFS-Discovery-Datei:

```
https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_ml/gbfs.json
```

Verwendete Feeds (deutsch):
- `station_information.json` — Stammdaten (Name, Koordinaten, Kapazität)
- `station_status.json` — aktuelle Verfügbarkeit (Räder, Docks, Renting/Returning-Status)

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows Git Bash; unter cmd/PowerShell: .venv\Scripts\activate
pip install -r requirements.txt
```

## Starten

Einmalig Stationsstammdaten holen:

```bash
python collector/stations.py
```

Dauerhaften Collector starten (fragt alle 10 Minuten `station_status.json` ab):

```bash
python collector/poll.py
```

Läuft als Endlosschleife im Vordergrund. **Stoppen mit Strg+C.** Der Collector sammelt nur
Daten, solange dieses Skript aktiv läuft und der Rechner an ist — es gibt aktuell keinen
Hintergrunddienst.

## Konfiguration

Über Umgebungsvariablen (oder `.env`-Datei im Projektroot, wird via `python-dotenv` geladen):

| Variable | Default | Bedeutung |
|---|---|---|
| `MYRADL_DATA_DIR` | `C:\Felix\MyRadl_Vorhersage\data` | Zielordner für alle CSV-Dateien |
| `MYRADL_POLL_INTERVAL_SECONDS` | `600` | Abfrageintervall in Sekunden |

Der Datenordner ist bewusst konfigurierbar, damit er später leicht z.B. auf eine externe
Platte oder einen Cloud-Mount umziehbar ist.

## Datenstruktur

Der Datenordner (`data/`, **nicht** im Git-Repo, siehe `.gitignore`) enthält:

- `stations.csv` — einmalig erzeugte Stationsstammdaten: `station_id, name, lat, lon,
  capacity, is_virtual_station`. Die meisten MyRadl-Stationen sind virtuelle
  Rückgabezonen ohne feste Kapazität, daher ist `capacity` bei den meisten Zeilen leer.
- `YYYY-MM-DD.csv` — eine Datei pro Tag (UTC-Datum), eine Zeile pro Station und Poll:
  `station_id, timestamp, bikes_available, docks_available, is_renting, is_returning`.
  `timestamp` ist UTC im ISO-Format.
- `weather.csv` — eine durchgehende Datei (kein Tages-Split, da winzig), eine Zeile pro
  Stunde: `timestamp, latitude, longitude, temperature_2m, precipitation, wind_speed_10m,
  relative_humidity_2m, weather_code`. Quelle: [Open-Meteo](https://open-meteo.com/)
  (kostenlos, kein API-Key). Abgefragt wird der geografische Schwerpunkt aller
  MyRadl-Stationen (aus `stations.csv` berechnet) — ein Wetterwert für die ganze Region,
  nicht pro Station, da sich Wetter über die ~45x50 km des Servicegebiets kaum unterscheidet.

Einzelne fehlgeschlagene Requests werden geloggt und der Collector macht beim nächsten
Intervall einfach weiter, statt abzustürzen.

## Cloud-Collector (GitHub Actions)

Damit die Erfassung nicht davon abhängt, dass der eigene Rechner läuft, gibt es zusätzlich
[.github/workflows/collect.yml](.github/workflows/collect.yml): ein Workflow, der per Cron
alle 10 Minuten `collector/poll.py --once` ausführt (und einmal pro Stunde zusätzlich
`collector/weather.py --once`) und die entstandenen CSVs auf einem eigenen, von main
getrennten Branch **`data`** committet.

- **main-Branch**: nur Code, bleibt sauber.
- **data-Branch**: nur `stations.csv` + `YYYY-MM-DD.csv`, wächst mit jedem Poll. Historie
  dort einsehbar/klonbar mit `git clone --branch data --single-branch <repo-url>`.
- Kostenlos, weil das Repo public ist (Standard-Runner sind für öffentliche Repos
  unbegrenzt kostenlos). Bei einem privaten Repo würde das 10-Minuten-Intervall das
  Freikontingent von 2.000 Minuten/Monat sprengen.
- GitHub garantiert bei `schedule`-Triggern kein exaktes Timing — Verzögerungen von
  5–30 Minuten sind normal, besonders zur vollen/halben Stunde. Für dieses Projekt
  unkritisch.
- Manuell auslösen: im GitHub-Repo unter Actions → "Collect MyRadl data" →
  "Run workflow".

## Bekannte Einschränkung

Lokal (`python collector/poll.py`) läuft der Collector nur, solange das Skript aktiv ist
und der Rechner läuft — es gibt Lücken bei Neustart, Schlafmodus oder Absturz. Der
GitHub-Actions-Workflow oben deckt das ab, solange das Repo public bleibt und niemand die
Scheduled Workflows deaktiviert (GitHub pausiert sie automatisch nach 60 Tagen Inaktivität
im Repo — dann reicht ein beliebiger Commit/Push, um sie zu reaktivieren).

Ausserdem haelt sich GitHub bei `schedule`-Triggern in der Praxis nicht an die
konfigurierten 15 Minuten: real kommen oft nur 6–30 Polls pro Tag mit Luecken von
30 Minuten bis über 2 Stunden an, statt der theoretischen ~96. Das Feature Engineering im
`model/`-Ordner geht davon bewusst aus (stündliches Resampling statt fester Lags).

## Vorhersagemodell + Karte (Prototyp)

Im `model/`-Ordner: XGBoost-Quantil-Modelle (P10/P50/P90), die `bikes_available` pro
Station für Horizonte 1–12h vorhersagen, plus eine interaktive Karte unter `docs/`.

```bash
pip install -r requirements-model.txt
python model/train.py
python model/generate_predictions.py
python -m http.server 8000 --directory docs   # lokal testen
```

Details, aktueller Modellstand und offene Punkte: [model/STATUS.md](model/STATUS.md).

`.github/workflows/predict.yml` trainiert stündlich neu und deployed die Karte auf den
`gh-pages`-Branch — Live-Version unter
[felix-schnell.github.io/MyRadl_Vorhersage](https://felix-schnell.github.io/MyRadl_Vorhersage/)
(sobald GitHub Pages im Repo aktiviert ist, siehe STATUS.md).
