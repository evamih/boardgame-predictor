import gzip
import html
import re
import sys
import xml.etree.ElementTree as ET

import pandas as pd

import config

LINK_TYPES = {
    "boardgamecategory": "categories",
    "boardgamemechanic": "mechanics",
    "boardgamefamily": "families",
    "boardgamedesigner": "designers",
    "boardgameartist": "artists",
    "boardgamepublisher": "publishers",
}

SIMPLE_FIELDS = {
    "year_published": ("yearpublished", int),
    "min_players": ("minplayers", int),
    "max_players": ("maxplayers", int),
    "playing_time": ("playingtime", int),
    "min_playtime": ("minplaytime", int),
    "max_playtime": ("maxplaytime", int),
    "min_age": ("minage", int),
    "users_rated": ("statistics/ratings/usersrated", int),
    "average_rating": ("statistics/ratings/average", float),
    "bayes_average": ("statistics/ratings/bayesaverage", float),
    "rating_stddev": ("statistics/ratings/stddev", float),
    "owned": ("statistics/ratings/owned", int),
    "trading": ("statistics/ratings/trading", int),
    "wanting": ("statistics/ratings/wanting", int),
    "wishing": ("statistics/ratings/wishing", int),
    "num_comments": ("statistics/ratings/numcomments", int),
    "num_weights": ("statistics/ratings/numweights", int),
    "average_weight": ("statistics/ratings/averageweight", float),
}

# helpers:

def to_number(text, cast):
    if text is None:
        return None
    try:
        return cast(float(text)) if cast is int else cast(text)
    except ValueError:
        return None


def value_of(item, path, cast):
    element = item.find(path)
    return to_number(element.get("value"), cast) if element is not None else None


def first_int(text):
    match = re.match(r"\d+", text or "")
    return int(match.group()) if match else None

# parsers:

def parse_links(item, row):
    values = {column: [] for column in LINK_TYPES.values()}
    n_expansions = 0
    is_reimplementation = False

    for link in item.findall("link"):
        link_type = link.get("type")
        if link_type in LINK_TYPES:
            values[LINK_TYPES[link_type]].append(link.get("value"))
        elif link_type == "boardgameexpansion":
            n_expansions += 1
        elif link_type == "boardgameimplementation" and link.get("inbound") != "true":
            is_reimplementation = True

    for column, names in values.items():
        row[column] = "|".join(names)
        row[f"n_{column}"] = len(names)

    row["n_expansions"] = n_expansions
    row["is_reimplementation"] = is_reimplementation
    row["is_crowdfunded"] = any(f.startswith("Crowdfunding:") for f in values["families"])

def parse_ranks(item, row):
    for rank in item.findall("statistics/ratings/ranks/rank"):
        name = rank.get("name")
        column = "rank_overall" if name == "boardgame" else f"rank_{name}"
        row[column] = to_number(rank.get("value"), int)

def parse_numplayers_poll(item, row):
    poll = item.find("poll[@name='suggested_numplayers']")
    row["numplayers_poll_votes"] = to_number(poll.get("totalvotes"), int) if poll is not None else None
    row["best_numplayers"] = None
    row["recommended_min"] = None
    row["recommended_max"] = None
    if poll is None:
        return

    best_count, best_votes = None, 0
    recommended = []
    for results in poll.findall("results"):
        count = first_int(results.get("numplayers"))
        votes = {r.get("value"): to_number(r.get("numvotes"), int) or 0 for r in results.findall("result")}
        best = votes.get("Best", 0)
        good = best + votes.get("Recommended", 0)
        if best > best_votes:
            best_count, best_votes = count, best
        if good > votes.get("Not Recommended", 0) and good > 0:
            recommended.append(count)

    row["best_numplayers"] = best_count
    if recommended:
        row["recommended_min"] = min(recommended)
        row["recommended_max"] = max(recommended)

def parse_playerage_poll(item, row):
    poll = item.find("poll[@name='suggested_playerage']")
    row["playerage_poll_votes"] = to_number(poll.get("totalvotes"), int) if poll is not None else None
    row["community_min_age"] = None
    if poll is None:
        return

    ages = []
    for r in poll.findall("results/result"):
        ages.append((first_int(r.get("value")), to_number(r.get("numvotes"), int) or 0))
    total = sum(votes for _, votes in ages)
    if total == 0:
        return
    running = 0
    for age, votes in sorted(ages):
        running += votes
        if running >= total / 2:
            row["community_min_age"] = age
            break

def parse_language_poll(item, row):
    poll = item.find("poll[@name='language_dependence']")
    row["langdep_poll_votes"] = to_number(poll.get("totalvotes"), int) if poll is not None else None
    row["language_dependence"] = None
    if poll is None:
        return

    best_level, best_votes = None, 0
    for r in poll.findall("results/result"):
        votes = to_number(r.get("numvotes"), int) or 0
        if votes > best_votes:
            best_level, best_votes = to_number(r.get("level"), int), votes
    row["language_dependence"] = best_level

def parse_item(item) -> dict:
    row = {"id": int(item.get("id"))}

    name = item.find("name[@type='primary']")
    row["name"] = name.get("value") if name is not None else None

    for column, (path, cast) in SIMPLE_FIELDS.items():
        row[column] = value_of(item, path, cast)

    description = html.unescape(item.findtext("description") or "")
    row["description_words"] = len(description.split())

    parse_links(item, row)
    parse_ranks(item, row)
    parse_numplayers_poll(item, row)
    parse_playerage_poll(item, row)
    parse_language_poll(item, row)
    
    return row

def parse_file(path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        root = ET.fromstring(f.read())
    return [parse_item(item) for item in root.findall("item")]

# main block:

def main() -> None:
    files = sorted(config.XML_DIR.glob("batch_*.xml.gz"))
    if not files:
        sys.exit(f"No batch files in {config.XML_DIR}. Run step 2 (fetch) first.")

    rows, failed_files = [], []
    for i, path in enumerate(files, 1):
        try:
            rows.extend(parse_file(path))
        except ET.ParseError as error:
            failed_files.append(path.name)
            print(f"  could not parse {path.name}: {error}")
        if i % 100 == 0 or i == len(files):
            print(f"  parsed {i}/{len(files)} files, {len(rows):,} games so far")

    df = pd.DataFrame(rows)
    before = len(df)
    df = df.drop_duplicates(subset="id").sort_values("id")

    config.PARSED_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.PARSED_CSV, index=False, encoding="utf-8")

    print(f"\nGames parsed: {len(df):,}  ({before - len(df)} duplicates removed)")
    print(f"Columns: {df.shape[1]}")
    print(f"Files that failed: {len(failed_files)} {failed_files if failed_files else ''}")
    print(f"Wrote {config.PARSED_CSV}")

if __name__ == "__main__":
    main()