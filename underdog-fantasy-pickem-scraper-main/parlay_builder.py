import json
import os
import random
from datetime import datetime, timezone
from itertools import combinations

import pandas as pd
import requests

# Primary stats to focus on per sport (more predictable, cleaner lines)
PRIMARY_STATS = {
    "NBA": ["Points", "Rebounds", "Assists", "Pts + Rebs + Asts", "3-Pointers Made"],
    "MLB": ["Hits", "Strikeouts", "Total Bases", "Hits + Runs + RBIs", "Runs", "Home Runs"],
    "NHL": ["Goals", "Assists", "Points", "Shots on Goal"],
}

TARGET_SPORTS = ["NBA", "MLB", "NHL"]

PARLAY_SIZES = [3, 4, 5, 6]

# Underdog Pick'em payouts by number of correct picks
PAYOUTS = {2: "3x", 3: "5x", 4: "10x", 5: "20x", 6: "40x"}


def load_config():
    path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def fetch_data(config):
    resp = requests.get(config["ud_pickem_url"], headers=config["headers"])
    if resp.status_code != 200:
        raise Exception(f"API request failed: {resp.status_code}")
    return resp.json()


def get_today_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def build_props_df(data, target_date=None):
    """Flatten API data into a clean props DataFrame for the target date."""
    if target_date is None:
        target_date = get_today_str()

    games = {g["id"]: g for g in data["games"]}
    appearances = {a["id"]: a for a in data["appearances"]}
    players = {p["id"]: p for p in data["players"]}

    # Filter games to today's target sports
    today_game_ids = {
        gid
        for gid, g in games.items()
        if g.get("scheduled_at", "").startswith(target_date)
        and g["sport_id"] in TARGET_SPORTS
        and g["status"] == "scheduled"
    }

    today_app_ids = {
        aid
        for aid, a in appearances.items()
        if a["match_id"] in today_game_ids
    }

    rows = []
    for line in data["over_under_lines"]:
        if line["status"] != "active":
            continue
        if line["line_type"] != "balanced":
            continue

        app_stat = line["over_under"]["appearance_stat"]
        app_id = app_stat["appearance_id"]
        if app_id not in today_app_ids:
            continue

        app = appearances[app_id]
        player = players.get(app.get("player_id", ""), {})
        game = games.get(app["match_id"], {})

        full_name = f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()
        sport = game.get("sport_id", "")
        stat = app_stat.get("display_stat", app_stat.get("stat", ""))
        stat_value = float(line["stat_value"])
        scheduled_at = game.get("scheduled_at", "")

        for opt in line["options"]:
            if opt.get("status") != "active":
                continue
            direction = "over" if opt["choice"] == "higher" else "under"
            rows.append(
                {
                    "player": full_name,
                    "sport": sport,
                    "game": game.get("title", ""),
                    "game_time": scheduled_at,
                    "stat": stat,
                    "line": stat_value,
                    "direction": direction,
                    "display": opt.get("choice_display_name_shorter", ""),
                    "american_odds": opt.get("american_price", ""),
                    "line_id": line["id"],
                }
            )

    return pd.DataFrame(rows)


def score_prop(row):
    """Higher score = better candidate for a parlay leg."""
    score = 0
    sport = row["sport"]
    stat = row["stat"]

    # Prefer primary stats
    if stat in PRIMARY_STATS.get(sport, []):
        score += 10

    # Prefer .5 lines (can't push)
    if row["line"] % 1 == 0.5:
        score += 5

    # Prefer over direction for offensive stats (standard pick'em lean)
    if row["direction"] == "over":
        score += 2

    # Prefer moderate lines (not too high, not too low) per sport
    if sport == "NBA":
        if stat == "Points" and 15 <= row["line"] <= 35:
            score += 3
        elif stat == "Rebounds" and 4.5 <= row["line"] <= 12:
            score += 3
        elif stat == "Assists" and 3.5 <= row["line"] <= 9:
            score += 3
        elif stat == "3-Pointers Made" and row["line"] <= 3.5:
            score += 3
    elif sport == "MLB":
        if stat == "Hits" and 0.5 <= row["line"] <= 2.5:
            score += 3
        elif stat == "Strikeouts" and 4.5 <= row["line"] <= 9.5:
            score += 3
        elif stat == "Total Bases" and 1.5 <= row["line"] <= 4.5:
            score += 3
        elif stat == "Hits + Runs + RBIs" and 1.5 <= row["line"] <= 4.5:
            score += 3
    elif sport == "NHL":
        if stat == "Shots on Goal" and 2.5 <= row["line"] <= 5.5:
            score += 3
        elif stat == "Goals" and row["line"] == 0.5:
            score += 2
        elif stat == "Points" and 0.5 <= row["line"] <= 1.5:
            score += 3

    return score


def select_parlay_legs(candidates_df, size, used_players=None, seed=None):
    """Select `size` legs from candidates ensuring player diversity."""
    if used_players is None:
        used_players = set()

    rng = random.Random(seed)
    df = candidates_df.copy()
    df = df[~df["player"].isin(used_players)]

    # Only one leg per player
    df = df.sort_values("score", ascending=False)

    chosen = []
    seen_players = set(used_players)
    seen_line_ids = set()

    rows = df.to_dict("records")
    rng.shuffle(rows)

    # Sort by score descending with slight shuffle for variety
    rows.sort(key=lambda r: r["score"] + rng.uniform(0, 2), reverse=True)

    for row in rows:
        if len(chosen) >= size:
            break
        if row["player"] in seen_players:
            continue
        if row["line_id"] in seen_line_ids:
            continue
        chosen.append(row)
        seen_players.add(row["player"])
        seen_line_ids.add(row["line_id"])

    return chosen if len(chosen) == size else None


def build_themed_parlays(props_df):
    """Build a set of themed parlays for today's games."""
    props_df = props_df.copy()
    props_df["score"] = props_df.apply(score_prop, axis=1)

    parlays = []

    # --- Sport-specific parlays ---
    for sport in TARGET_SPORTS:
        sport_df = props_df[
            (props_df["sport"] == sport)
            & (props_df["stat"].isin(PRIMARY_STATS.get(sport, [])))
        ]
        if sport_df.empty:
            continue

        for size in PARLAY_SIZES:
            if len(sport_df["player"].unique()) < size:
                continue
            for seed in range(5):  # generate a few variants
                legs = select_parlay_legs(sport_df, size, seed=seed * 17 + hash(sport))
                if legs:
                    parlays.append(
                        {
                            "theme": f"{sport} {size}-pick",
                            "sport": sport,
                            "size": size,
                            "payout": PAYOUTS.get(size, "?"),
                            "legs": legs,
                        }
                    )
                    break  # one parlay per sport/size combo

    # --- Cross-sport "Best of the Day" parlays ---
    primary_df = props_df[
        props_df.apply(
            lambda r: r["stat"] in PRIMARY_STATS.get(r["sport"], []), axis=1
        )
    ]
    for size in [4, 5, 6]:
        if len(primary_df["player"].unique()) < size:
            continue
        for seed in range(10):
            legs = select_parlay_legs(primary_df, size, seed=seed * 13 + 7)
            if legs:
                parlays.append(
                    {
                        "theme": f"Cross-Sport {size}-pick",
                        "sport": "MULTI",
                        "size": size,
                        "payout": PAYOUTS.get(size, "?"),
                        "legs": legs,
                    }
                )
                break

    return parlays


def print_parlays(parlays):
    print("\n" + "=" * 65)
    print(f"  UNDERDOG FANTASY PARLAY SUGGESTIONS — {get_today_str()}")
    print("=" * 65)

    for parlay in parlays:
        print(f"\n{'─' * 65}")
        print(
            f"  {parlay['theme'].upper()}  |  Payout: {parlay['payout']}  |  Sport: {parlay['sport']}"
        )
        print(f"{'─' * 65}")
        for i, leg in enumerate(parlay["legs"], 1):
            print(
                f"  {i}. {leg['player']:<25} {leg['direction'].upper():<6} "
                f"{leg['stat']:<22} {leg['line']}  [{leg['game']}]"
            )

    print(f"\n{'=' * 65}\n")


def save_parlays_csv(parlays, output_path="parlays.csv"):
    rows = []
    for parlay in parlays:
        for i, leg in enumerate(parlay["legs"], 1):
            rows.append(
                {
                    "parlay_theme": parlay["theme"],
                    "payout": parlay["payout"],
                    "leg_number": i,
                    "player": leg["player"],
                    "sport": leg["sport"],
                    "game": leg["game"],
                    "game_time_utc": leg["game_time"],
                    "stat": leg["stat"],
                    "line": leg["line"],
                    "direction": leg["direction"],
                    "display": leg["display"],
                    "american_odds": leg["american_odds"],
                }
            )
    df = pd.DataFrame(rows)
    df.to_csv(output_path, index=False)
    print(f"Parlays saved to {output_path}")
    return df


def main():
    config = load_config()
    print(f"Fetching Underdog Fantasy props for {get_today_str()}...")
    data = fetch_data(config)

    props_df = build_props_df(data)

    if props_df.empty:
        print("No active balanced props found for today's games.")
        return

    sports_found = props_df["sport"].unique()
    games_found = props_df["game"].unique()
    print(f"Found {len(props_df)} prop options across {len(games_found)} games: {', '.join(games_found)}")

    parlays = build_themed_parlays(props_df)

    if not parlays:
        print("Could not build any parlays from today's data.")
        return

    print_parlays(parlays)
    save_parlays_csv(parlays)


if __name__ == "__main__":
    main()
