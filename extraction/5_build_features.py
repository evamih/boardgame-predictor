import sys
import re
import json

import numpy as np
import pandas as pd

import config

UNCREDITED = "(Uncredited)" # unknown designer

# easy to compute features from game launch:
 
def add_tier1_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["player_range"] = df["max_players"] - df["min_players"]
    df["is_solo"] = (df["min_players"] == 1).astype(int)
    df["is_two_player_only"] = ((df["min_players"] == 2) & (df["max_players"] == 2)).astype(int)
    df["log_playing_time"] = np.log1p(df["playing_time"])
    df["playtime_spread"] = df["max_playtime"] - df["min_playtime"]
    df["game_age"] = config.REFERENCE_YEAR - df["year_published"]
    for column in ["is_crowdfunded", "is_reimplementation"]:
        df[column] = df[column].astype(bool).astype(int)
    return df

# helpers:

def to_lists(series: pd.Series) -> pd.Series:
    return series.fillna("").map(lambda text: text.split("|") if text else [])

# column naming:
def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")

# encoding per feature column:
def add_multi_hot(df, lists, prefix, top_k, train_mask):
    counts = lists[train_mask].explode().value_counts()
    top_values = counts.head(top_k).index.tolist()
    new_columns = {}
    for value in top_values:
        name = f"{prefix}_{slug(value)}"
        new_columns[name] = lists.map(lambda items, v=value: int(v in items))
    return pd.concat([df, pd.DataFrame(new_columns, index=df.index)], axis=1), list(new_columns)

def add_tier2_features(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    train_mask = df["year_published"] <= config.TRAIN_END_YEAR
    created = []

    df, cols = add_multi_hot(df, to_lists(df["mechanics"]), "mech", config.TOP_MECHANICS, train_mask)
    created += cols
    df, cols = add_multi_hot(df, to_lists(df["categories"]), "cat", config.TOP_CATEGORIES, train_mask)
    created += cols

    families = to_lists(df["families"]).map(
        lambda items: [f.split(":", 1)[1].strip() for f in items
                       if f.startswith(config.FAMILY_PREFIXES)])
    df, cols = add_multi_hot(df, families, "fam", config.TOP_FAMILIES, train_mask)
    created += cols
    return df, created

# at first i wanted to add the publisher track record as a tier 3 feature but i noticed that:
# Leakage check: the number of publishers listed for a game correlates with its number of ratings (Spearman ρ = 0.51), 
# because BGG aggregates all localized editions. Example: Catan lists 50+ publishers, mostly foreign-language localizers.
# → n_publishers and publisher-based features are excluded from the pre-release model.

# designer track record:
def add_tier3_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Move 1: one row per (game, designer) pair.
    pairs = df[["id", "year_published", "average_rating", "average_weight"]].copy()
    pairs["designer"] = to_lists(df["designers"])
    pairs = pairs.explode("designer")
    pairs = pairs[pairs["designer"].notna() & (pairs["designer"] != UNCREDITED)]

    # Move 2: per designer and year, how many games and the sums of their scores.
    per_year = (pairs.groupby(["designer", "year_published"])
                .agg(games=("id", "size"),
                     rating_sum=("average_rating", "sum"),
                     weight_sum=("average_weight", "sum"),
                     weight_n=("average_weight", "count"))
                .reset_index()
                .sort_values(["designer", "year_published"]))

    # Move 3: running totals of strictly earlier years.
    grouped = per_year.groupby("designer")
    for column in ["games", "rating_sum", "weight_sum", "weight_n"]:
        per_year[f"prior_{column}"] = grouped[column].cumsum() - per_year[column]

    per_year["prior_mean_rating"] = per_year["prior_rating_sum"] / per_year["prior_games"]
    per_year["prior_mean_weight"] = per_year["prior_weight_sum"] / per_year["prior_weight_n"]
    per_year = per_year.replace([np.inf, -np.inf], np.nan)

    # Move 4: back to one row per game.
    pairs = pairs.merge(
        per_year[["designer", "year_published", "prior_games", "prior_mean_rating", "prior_mean_weight"]],
        on=["designer", "year_published"], how="left")

    per_game = pairs.groupby("id").agg(
        designer_prior_games=("prior_games", "max"),
        designer_prior_mean_rating=("prior_mean_rating", "mean"),
        designer_prior_mean_weight=("prior_mean_weight", "mean"),
    )
    df = df.merge(per_game, left_on="id", right_index=True, how="left")

    df["has_known_designer"] = df["id"].isin(pairs["id"]).astype(int)
    df["designer_prior_games"] = df["designer_prior_games"].fillna(0).astype(int)
    df["is_debut"] = ((df["has_known_designer"] == 1) & (df["designer_prior_games"] == 0)).astype(int)
    return df

# limitations for this feature:
# The earlier games' ratings are today's ratings, not their ratings at the time.
# Only games in your dataset (100+ ratings) count as earlier games, so a designer's obscure early titles are invisible. 
# The feature really means "earlier well-known games".

def build_groups(df: pd.DataFrame, multi_hot: list[str]) -> dict:
    pre_release = [
        "min_players", "max_players", "playing_time", "min_playtime", "max_playtime", "min_age",
        "player_range", "is_solo", "is_two_player_only", "log_playing_time", "playtime_spread",
        "is_crowdfunded", "is_reimplementation",
        "n_mechanics", "n_categories", "n_designers", "n_artists", "description_words",
        "designer_prior_games", "designer_prior_mean_rating", "designer_prior_mean_weight",
        "has_known_designer", "is_debut",
    ] + multi_hot
    groups = {
        "meta": ["id", "name", "year_published", "game_age"], # EDA only
        "pre_release": pre_release,
        "community": ["best_numplayers", "recommended_min", "recommended_max",
                      "community_min_age", "language_dependence"],
        "popularity": ["users_rated", "owned", "trading", "wanting", "wishing", "num_comments", # EDA only
                       "num_weights", "bayes_average", "rating_stddev",
                       "n_expansions", "n_publishers", "n_families", 'numplayers_poll_votes', 'playerage_poll_votes', 'langdep_poll_votes']
                      + [c for c in df.columns if c.startswith("rank_")],
        "lists": ["categories", "mechanics", "families", "designers", "artists", "publishers"],
        "targets": ["average_weight", "complexity_class", "average_rating", "highly_rated"],
    }
    listed = [c for columns in groups.values() for c in columns]
    unlisted = [c for c in df.columns if c not in listed]
    if unlisted:
        sys.exit(f"Columns not in any group: {unlisted}")
    missing = [c for c in listed if c not in df.columns]
    duplicated = sorted({c for c in listed if listed.count(c) > 1})
    if missing or duplicated:
        sys.exit(f"Feature groups are inconsistent. Missing: {missing}  In two groups: {duplicated}")
    return groups

def main() -> None:
    if not config.CLEAN_CSV.exists():
        sys.exit(f"{config.CLEAN_CSV} not found. Run step 04 first.")
    df = pd.read_csv(config.CLEAN_CSV, low_memory=False)

    df = add_tier1_features(df)
    df, multi_hot = add_tier2_features(df)
    df = add_tier3_features(df)
    groups = build_groups(df, multi_hot)

    df.to_csv(config.FEATURES_CSV, index=False, encoding="utf-8")
    config.FEATURE_GROUPS_JSON.write_text(json.dumps(groups, indent=2), encoding="utf-8")

    print(f"{len(df):,} games, {df.shape[1]} columns -> {config.FEATURES_CSV.name}")
    for name, columns in groups.items():
        print(f"  {name:<12}{len(columns):>4} columns")
    print(f"\nMulti-hot columns: {len(multi_hot)} "
          f"({config.TOP_MECHANICS} mechanics, {config.TOP_CATEGORIES} categories, "
          f"{config.TOP_FAMILIES} theme/component tags)")
    print("  first few:", ", ".join(multi_hot[:5]), "...")

    print("\nDesigner track record")
    print(f"  games with a known designer:        {df['has_known_designer'].mean():.1%}")
    print(f"  debut games (no earlier game):      {df['is_debut'].mean():.1%}")
    print(f"  games with an earlier-rated record: {df['designer_prior_mean_rating'].notna().mean():.1%}")
    print(f"\nWrote {config.FEATURE_GROUPS_JSON.name}")


if __name__ == "__main__":
    main()