import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.environ.get("MYRADL_DATA_DIR", r"C:\Felix\MyRadl_Vorhersage\data"))

GBFS_BASE_URL = "https://gbfs.nextbike.net/maps/gbfs/v2/nextbike_ml/de"
STATION_INFORMATION_URL = f"{GBFS_BASE_URL}/station_information.json"
STATION_STATUS_URL = f"{GBFS_BASE_URL}/station_status.json"

POLL_INTERVAL_SECONDS = int(os.environ.get("MYRADL_POLL_INTERVAL_SECONDS", "600"))
