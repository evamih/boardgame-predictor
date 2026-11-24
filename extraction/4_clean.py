import sys

import numpy as np
import pandas as pd

import config

ZERO_MEANS_UNKNOWN = [
    "year_published", "min_players", "max_players",
    "playing_time", "min_playtime", "max_playtime", "min_age",
]

POLL_ANSWERS = {
    "numplayers_poll_votes": ["best_numplayers", "recommended_min", "recommended_max"],
    "playerage_poll_votes": ["community_min_age"],
    "langdep_poll_votes": ["language_dependence"],
}

def zeros_to_missing(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for column in ZERO_MEANS_UNKNOWN:
        df[column] = df[column].mask(df[column] == 0)
    df["average_weight"] = df["average_weight"].mask(df["num_weights"].fillna(0) == 0)
    reversed_rows = df["max_players"] < df["min_players"]
    df.loc[reversed_rows, ["min_players", "max_players"]] = np.nan
    return df

def drop_unreliable_polls(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for votes_column, answer_columns in POLL_ANSWERS.items():
        too_few = df[votes_column].fillna(0) < config.MIN_POLL_VOTES
        df.loc[too_few, answer_columns] = np.nan
    return df

def keep_modern_released(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    year = df["year_published"]
    counts = {
        "unknown year": int(year.isna().sum()),
        f"before {config.MIN_YEAR}": int((year < config.MIN_YEAR).sum()),
        f"after {config.MAX_YEAR}": int((year > config.MAX_YEAR).sum()),
    }
    keep = year.between(config.MIN_YEAR, config.MAX_YEAR)
    return df[keep].copy(), counts

# target definition:

def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["complexity_class"] = pd.cut(
        df["average_weight"],
        bins=[-np.inf, config.LIGHT_MAX_WEIGHT, config.MEDIUM_MAX_WEIGHT, np.inf],
        labels=["light", "medium", "heavy"],
        right=False,
    )
    df["highly_rated"] = (df["average_rating"] >= config.HIGH_RATING).astype(int)
    return df

def main() -> None:
    if not config.PARSED_CSV.exists():
        sys.exit(f"{config.PARSED_CSV} not found. Run step 03 first.")
    df = pd.read_csv(config.PARSED_CSV, low_memory=False)
    n_in = len(df)

    df = zeros_to_missing(df)
    df = drop_unreliable_polls(df)
    df, removed = keep_modern_released(df)
    df = add_targets(df)

    df = df.drop(columns=["rank_boardgameaccessory", "rank_rpgitem"], errors="ignore") # only one game included

    df.to_csv(config.CLEAN_CSV, index=False, encoding="utf-8")

    print(f"Rows in:  {n_in:,}")
    for reason, count in removed.items():
        print(f"  removed ({reason}): {count:,}")
    print(f"Rows out: {len(df):,}   Columns: {df.shape[1]}")

    print("\nTargets")
    weight_known = df["average_weight"].notna().sum()
    print(f"  average_weight known for {weight_known:,} games "
          f"({weight_known / len(df):.1%})")
    print("  complexity_class (% of games with known weight):")
    shares = df["complexity_class"].value_counts(normalize=True) * 100
    for label in ["light", "medium", "heavy"]:
        print(f"    {label:<7}{shares.get(label, 0):5.1f}%")
    print(f"  highly_rated (rating >= {config.HIGH_RATING}): {df['highly_rated'].mean():.1%} of games")

    print("\nMissing after cleaning (% of rows)")
    check = ["min_players", "max_players", "playing_time", "min_age", "average_weight",
             "best_numplayers", "community_min_age", "language_dependence"]
    print((df[check].isna().mean() * 100).round(1).to_string())
    print(f"\nWrote {config.CLEAN_CSV}")


if __name__ == "__main__":
    main()