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

CLEAN_CSV = DATA_PROCESSED / "games_clean.csv"

MIN_YEAR = 1950          # older "games" are traditional, not designed products
MAX_YEAR = 2025          # newer games are unreleased or have too little rating history
REFERENCE_YEAR = 2026    # year the data was collected; used for game_age
MIN_POLL_VOTES = 10      # poll answers with fewer votes are treated as unknown
LIGHT_MAX_WEIGHT = 2.0   # complexity classes: light < 2 <= medium < 3 <= heavy
MEDIUM_MAX_WEIGHT = 3.0
HIGH_RATING = 7.0        # highly_rated = average_rating >= 7

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