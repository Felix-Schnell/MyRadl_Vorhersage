import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.environ.get("MYRADL_DATA_DIR", r"C:\Felix\MyRadl_Vorhersage\data"))

GBFS_BASE_URL = "https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_ml/de"
STATION_INFORMATION_URL = f"{GBFS_BASE_URL}/station_information.json"
STATION_STATUS_URL = f"{GBFS_BASE_URL}/station_status.json"

POLL_INTERVAL_SECONDS = int(os.environ.get("MYRADL_POLL_INTERVAL_SECONDS", "600"))

WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_INTERVAL_SECONDS = int(os.environ.get("MYRADL_WEATHER_INTERVAL_SECONDS", "3600"))

# Geografischer Schwerpunkt aller MyRadl-Stationen (Region MVV), wird verwendet falls
# stations.csv noch nicht existiert. Ermittelt aus dem tatsaechlichen Stationsnetz
# (786 Stationen, lat 47.85-48.33, lon 11.15-11.76).
FALLBACK_LAT = 48.1437
FALLBACK_LON = 11.5552
