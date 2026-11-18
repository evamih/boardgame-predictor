import argparse
import sys
from pathlib import Path
import pandas as pd

import config # for constants and functions

REQUIRED_COLUMNS = ["id", "name", "yearpublished", "usersrated", "is_expansion"]
OUTPUT_COLUMNS = ["id", "name", "yearpublished", "usersrated"]

# %% helper functions:

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Select board game IDs to fetch from BGG.")
    parser.add_argument("--input", type=Path, default=None,
                        help="Path to the ranks dump (.zip or .csv).")
    parser.add_argument("--min-ratings", type=int, default=config.MIN_RATINGS,
                        help="Minimum number of user ratings.")
    parser.add_argument("--max-games", type=int, default=None,
                        help="Optional cap; take a random sample of this size.")
    parser.add_argument("--seed", type=int, default=config.RANDOM_SEED,
                        help="Random seed for the optional sample.")
    return parser.parse_args()

def find_input(path_arg: Path | None) -> Path:
    if path_arg is not None:
        if not path_arg.exists():
            sys.exit(f"Input file not found: {path_arg}")
        return path_arg
    for pattern in config.RANKS_DUMP_PATTERNS:
        matches = sorted(config.DATA_RAW.glob(pattern))
        if matches:
            if len(matches) > 1:
                print(f"Found {len(matches)} dumps matching {pattern}. Using the newest.")
            return matches[-1]
    expected = "\n  ".join(config.RANKS_DUMP_PATTERNS)
    sys.exit(f"Ranks dump not found in {config.DATA_RAW}. Save it as one of:\n  {expected}")

def load_dump(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df.columns = [c.strip().lower() for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        sys.exit(f"The dump is missing expected column(s): {missing}\n"
            f"Columns actually in the file: {list(df.columns)}")
    return df

def clean_types(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["id"] = pd.to_numeric(df["id"], errors="coerce")
    df["usersrated"] = pd.to_numeric(df["usersrated"], errors="coerce").fillna(0)
    df["is_expansion"] = pd.to_numeric(df["is_expansion"], errors="coerce").fillna(0)
    df["yearpublished"] = pd.to_numeric(df["yearpublished"], errors="coerce")

    df = df.dropna(subset=["id"])
    df["id"] = df["id"].astype(int)
    df = df.drop_duplicates(subset="id")
    return df

# %% main

def main() -> None:
    args = parse_args()
    input_path = find_input(args.input)
    print(f"Reading {input_path}")

    df = clean_types(load_dump(input_path))
    n_total = len(df)

    # 1 - base games only
    base = df[df["is_expansion"] == 0]
    n_expansions = n_total - len(base)

    # 2 - min 100 user ratings for stable avg
    rated = base[base["usersrated"] >= args.min_ratings]
    n_low_rated = len(base) - len(rated)

    # 3 - optional random sample max cap
    selected = rated
    sampled = False
    if args.max_games is not None and len(rated) > args.max_games:
        selected = rated.sample(n=args.max_games, random_state = args.seed)
        sampled = True

    # 4 - fixed order (sort by id)
    selected = selected.sort_values("id")[OUTPUT_COLUMNS]

    ## save + report

    config.SELECTED_IDS_CSV.parent.mkdir(parents=True, exist_ok=True)
    selected.to_csv(config.SELECTED_IDS_CSV, index=False)

    n_selected = len(selected)
    n_requests = -(-n_selected // config.BATCH_SIZE) # ceiling div (rounds up instead of down from //)
    est_minutes = n_requests * config.DELAY_SECONDS / 60
    years = selected["yearpublished"]
    years = years[years > 0] # 0 used for unknown year

    print("\nSelection report:")
    print(f"  rows in dump:              {n_total:,}")
    print(f"  removed (expansions):      {n_expansions:,}")
    print(f"  removed (too few ratings): {n_low_rated:,}  (min = {args.min_ratings})")
    if sampled:
        print(f"  removed (sample cap):      {len(rated) - n_selected:,}")
    print(f"  selected games:            {n_selected:,}")
    if not years.empty:
        print(f"  year range (known years):  {int(years.min())} - {int(years.max())}")
    print(f"  API requests needed:       {n_requests:,}  ({config.BATCH_SIZE} games each)")
    print(f"  estimated fetch time:      ~{est_minutes:.0f} min at {config.DELAY_SECONDS}s per request")
    print(f"\nWrote {config.SELECTED_IDS_CSV}")

if __name__ == "__main__":
    main()