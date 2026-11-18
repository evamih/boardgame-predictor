import os 
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent # gets the root of the project for each operation

# file names + path constants:
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"

RANKS_DUMP_CANDIDATES = [
    DATA_RAW / "boardgames_ranks.csv",
    DATA_RAW / "boardgames_ranks.zip",
]
RANKS_DUMP_PATTERNS = [
    "boardgames_ranks*.csv",
    "boardgames_ranks*.zip",
]
SELECTED_IDS_CSV = DATA_RAW / "selected_ids.csv"
XML_DIR = DATA_RAW / "bgg_xml"
FETCH_LOG_CSV = DATA_RAW / "fetch_log.csv"
PARSED_CSV = DATA_PROCESSED / "games_parsed.csv"

# other constant parameters:
MIN_RATINGS = 100
RANDOM_SEED = 42

API_URL = "https://boardgamegeek.com/xmlapi2/thing"
BATCH_SIZE = 20
DELAY_SECONDS = 5
USER_AGENT = "BGG-course-project/1.0 (non-commercial university data science project)" # bgg server introduction (for good etiquette)

# token fetch:

def get_token() -> str:
    token = os.environ.get("BGG_TOKEN")
    env_file = ROOT / ".env"
    if not token and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("BGG_TOKEN="):
                token = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not token:
        raise SystemExit("BGG_TOKEN not found in environment variables or .env file")
    return token