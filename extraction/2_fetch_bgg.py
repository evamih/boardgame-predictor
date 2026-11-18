import argparse
import csv
import gzip
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pandas as pd
import requests

import config

MAX_ATTEMPTS = 6          # tries per batch before giving up on it
MAX_WAIT_SECONDS = 120    # upper limit for the growing wait between retries
RETRY_STATUS = {202, 429, 500, 502, 503, 504}
LOG_COLUMNS = ["batch", "n_requested", "n_returned", "missing_ids", "attempts", "fetched_at_utc"]

class PoliteClock:
    def __init__(self, delay: float):
        self.delay = delay
        self.last_request = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self.last_request
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self.last_request = time.monotonic()

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch selected games from the BGG XML API2.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only process the first N batches (for a pilot run).")
    return parser.parse_args()

def load_batches() -> list[list[int]]:
    if not config.SELECTED_IDS_CSV.exists():
        sys.exit(f"{config.SELECTED_IDS_CSV} not found. Run step 1 first.")
    ids = pd.read_csv(config.SELECTED_IDS_CSV)["id"].astype(int).tolist()
    size = config.BATCH_SIZE
    return [ids[start:start + size] for start in range(0, len(ids), size)]

def batch_path(batch_number: int):
    return config.XML_DIR / f"batch_{batch_number:05d}.xml.gz"

def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {config.get_token()}",
        "User-Agent": config.USER_AGENT,
    })
    return session

# script fct:

def fetch_batch(session, clock, ids):
    params= {"id": ",".join(str(i) for i in ids), "type": "boardgame", "stats": 1}

    for attempt in range(1, MAX_ATTEMPTS+1):
        clock.wait()
        try:
            response = session.get(config.API_URL, params=params, timeout=60)
        except (requests.ConnectionError, requests.Timeout) as error:
            problem = f"network error ({type(error).__name__})"
        else:
            if response.status_code == 200 and "<items" in response.text:
                return response.text, attempt
            if response.status_code == 401:
                sys.exit("401 Unauthorized: BGG rejected the token. Check BGG_TOKEN in .env "
                         "and that API_URL has no 'www.'.")
            if response.status_code not in RETRY_STATUS and response.status_code != 200:
                sys.exit(f"Unexpected status {response.status_code}. First part of the reply:\n"
                         f"{response.text[:500]}")
            problem = f"status {response.status_code}"

        wait = min(config.DELAY_SECONDS * 2 ** attempt, MAX_WAIT_SECONDS)
        print(f"    {problem} - attempt {attempt}/{MAX_ATTEMPTS}, waiting {wait}s")
        time.sleep(wait)

    raise RuntimeError(f"giving up after {MAX_ATTEMPTS} attempts")

def returned_ids(xml_text: str) -> set[int]:
    root = ET.fromstring(xml_text)
    return {int(item.get("id")) for item in root.findall("item")}

# save + log:

def save_atomically(path, xml_text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        f.write(xml_text)
    tmp.replace(path)


def append_log(row: dict) -> None:
    new_file = not config.FETCH_LOG_CSV.exists()
    with open(config.FETCH_LOG_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow(row)

# main loop:

def main() -> None:
    args = parse_args()
    batches = load_batches()
    if args.limit is not None:
        batches = batches[:args.limit]

    config.XML_DIR.mkdir(parents=True, exist_ok=True)
    todo = [n for n in range(1, len(batches)+1) if not batch_path(n).exists()]
    print(f"{len(batches)} batches in total, {len(batches) - len(todo)} already on disk, "
          f"{len(todo)} to fetch (~{len(todo) * config.DELAY_SECONDS / 60:.0f} min).")
    if not todo:
        return

    session = make_session()
    clock = PoliteClock(config.DELAY_SECONDS)
    failed = []
    start = time.monotonic()

    try:
        for done, n in enumerate(todo, 1):
            ids = batches[n-1]
            try:
                xml_text, attempts = fetch_batch(session, clock, ids)
            except RuntimeError as error:
                print(f"  batch {n}: FAILED ({error}); it will be retried on the next run")
                failed.append(n)
                continue

            save_atomically(batch_path(n), xml_text)
            missing = sorted(set(ids) - returned_ids(xml_text))
            append_log({
                "batch": n,
                "n_requested": len(ids),
                "n_returned": len(ids) - len(missing),
                "missing_ids": " ".join(map(str, missing)),
                "attempts": attempts,
                "fetched_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })

            per_batch = (time.monotonic()-start) / done
            eta_min = per_batch * (len(todo) - done) / 60
            note = f", {len(missing)} missing" if missing else ""
            print(f"  batch {n:>4}/{len(batches)} saved ({len(ids) - len(missing)} games{note}) "
                  f"- ~{eta_min:.0f} min left")

    except KeyboardInterrupt:
        print("\nStopped by you (Ctrl+C). Re-run the same command to continue where it left off.")
        return

    print(f"\nFinished. {len(todo) - len(failed)} batches saved, {len(failed)} failed.")
    if failed:
        print("Re-run to retry the failed batches:", failed)

if __name__ == "__main__":
    main()