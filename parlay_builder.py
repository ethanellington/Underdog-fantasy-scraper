"""
Underdog Fantasy Parlay Builder
Scrapes live props and suggests parlays based on payout value.

Modes:
  balanced  – targets mainstream stats near fair value (1.0–1.15x boost)
  value     – maximizes payout_multiplier (higher risk, longer shots)
"""

import pandas as pd
from underdog_scraper import UnderdogScraper

# Underdog payout multipliers by pick count
PAYOUT_TABLE = {
    2: {"power": 3.0,  "flex": 1.5},
    3: {"power": 6.0,  "flex": 2.25},
    4: {"power": 10.0, "flex": 5.0},
    5: {"power": 20.0, "flex": 6.0},
    6: {"power": 40.0, "flex": 7.5},
}

# Mainstream stats to focus on in balanced mode
MAINSTREAM_STATS = {
    "NBA": ["points", "rebounds", "assists", "pts_rebs_asts", "three_points_made"],
    "MLB": ["hits", "total_bases", "strikeouts", "runs", "rbis"],
    "NHL": ["shots", "points", "assists", "goals"],
    "PGA": ["birdies_or_better", "strokes"],
    "WNBA": ["points", "rebounds", "assists"],
    "MMA": ["strikes_landed", "takedowns"],
    "TENNIS": ["games_won", "sets_won"],
}

# Any stat with huge boosts (>4x) is a long-shot; exclude from balanced mode
LONGSHOT_MULTIPLIER_THRESHOLD = 4.0


def fetch_props():
    print("Fetching live props from Underdog Fantasy...")
    scraper = UnderdogScraper()
    scraper.scrape()
    return scraper.underdog_props


def prep_df(df, sport=None, mode="balanced"):
    work = df.copy()
    work["payout_multiplier"] = pd.to_numeric(work["payout_multiplier"], errors="coerce").fillna(1.0)

    if sport:
        sports = [sport] if isinstance(sport, str) else sport
        work = work[work["sport_id"].isin(sports)]

    if mode == "balanced":
        # Keep only core stats
        mainstream_mask = pd.Series(False, index=work.index)
        for s, stats in MAINSTREAM_STATS.items():
            mainstream_mask |= (work["sport_id"] == s) & (work["stat_name"].isin(stats))
        # For sports not in dict, keep all their stats
        unknown = ~work["sport_id"].isin(MAINSTREAM_STATS.keys())
        work = work[mainstream_mask | unknown]

        # Drop longshots
        work = work[work["payout_multiplier"] < LONGSHOT_MULTIPLIER_THRESHOLD]

    # Remove alternate lines from balanced mode (stick to standard lines)
    if mode == "balanced":
        work = work[work["line_type"] == "balanced"]

    return work.reset_index(drop=True)


def score_leg(row, mode="balanced"):
    pm = float(row["payout_multiplier"])
    if mode == "balanced":
        # Best score = multiplier just above 1.0 (slight edge, not a longshot)
        return pm
    else:
        return pm  # value mode: raw multiplier wins


def build_parlays(df, sport=None, num_picks=4, n_parlays=5, mode="balanced"):
    work = prep_df(df, sport=sport, mode=mode)

    if work.empty:
        print(f"  No props match (sport={sport}, mode={mode})")
        return []

    work["leg_score"] = work.apply(lambda r: score_leg(r, mode), axis=1)

    # Keep best leg per player per stat_name
    work = (
        work
        .sort_values("leg_score", ascending=False)
        .drop_duplicates(subset=["player_id", "stat_name"], keep="first")
        .reset_index(drop=True)
    )

    if len(work) < num_picks:
        print(f"  Not enough unique props ({len(work)}) for {num_picks}-pick parlay.")
        return []

    parlays = []
    used_players = set()

    for _ in range(n_parlays):
        candidate = work[~work["player_id"].isin(used_players)]
        if len(candidate) < num_picks:
            candidate = work
            used_players = set()

        # Diversify: rotate through sports within the parlay
        legs_rows = []
        remaining = candidate.copy()
        sports_seen = {}
        while len(legs_rows) < num_picks and not remaining.empty:
            # Pick the best leg we haven't used yet, prefer a different sport
            best_idx = remaining.index[0]
            best_sport = remaining.loc[best_idx, "sport_id"]
            sport_count = sports_seen.get(best_sport, 0)
            if sport_count >= 2 and len(remaining) > 1:
                # Try next candidate from a different sport
                alt = remaining[remaining["sport_id"] != best_sport]
                if not alt.empty:
                    best_idx = alt.index[0]
                    best_sport = alt.loc[best_idx, "sport_id"]
            legs_rows.append(remaining.loc[best_idx])
            sports_seen[best_sport] = sports_seen.get(best_sport, 0) + 1
            remaining = remaining.drop(best_idx)

        if len(legs_rows) < num_picks:
            # Fall back to top picks without diversity constraint
            legs_rows = [candidate.iloc[i] for i in range(min(num_picks, len(candidate)))]

        parlay = pd.DataFrame(legs_rows)[
            ["full_name", "sport_id", "team_id", "position_name",
             "stat_name", "stat_value", "choice", "line_type", "payout_multiplier"]
        ].reset_index(drop=True)
        parlays.append(parlay)
        used_players.update(row["player_id"] for row in legs_rows)

    return parlays


def print_parlay(parlay, idx, num_picks, mode="balanced"):
    payout = PAYOUT_TABLE.get(num_picks, {})
    power = payout.get("power", "?")
    flex = payout.get("flex", "?")
    mode_label = "BALANCED" if mode == "balanced" else "VALUE"

    print(f"\n{'='*65}")
    print(f"  [{mode_label}] PARLAY #{idx+1}  —  {num_picks}-Pick  |  Power: {power}x  /  Flex: {flex}x")
    print(f"{'='*65}")
    for i, row in parlay.iterrows():
        pm = float(row["payout_multiplier"])
        boost_note = f"  [x{pm:.2f}]" if pm != 1.0 else ""
        alt_note = "  [ALT]" if row["line_type"] == "alternate" else ""
        stat = row["stat_name"].replace("_", " ").title()
        line = f"  {i+1}. {row['full_name']} ({row['sport_id']} {row['position_name']}) — "
        line += f"{stat} {row['choice'].upper()} {row['stat_value']}{alt_note}{boost_note}"
        print(line)


def print_sport_summary(df):
    print("\nProps available by sport:")
    by_sport = (
        df.groupby("sport_id")
        .agg(players=("player_id", "nunique"), legs=("player_id", "count"))
        .sort_values("players", ascending=False)
    )
    for sport, row in by_sport.iterrows():
        print(f"  {sport:8s}  {row['players']:3d} players  {row['legs']:4d} legs")


def main():
    df = fetch_props()
    df["payout_multiplier"] = pd.to_numeric(df["payout_multiplier"], errors="coerce").fillna(1.0)

    print(f"\nLoaded {len(df)} prop legs across {df['sport_id'].nunique()} sports.")
    print_sport_summary(df)

    # ── BALANCED PARLAYS ────────────────────────────────────────────────────────
    print("\n\n" + "─"*65)
    print("  BALANCED PARLAYS  (mainstream stats, near fair-value lines)")
    print("─"*65)

    print("\n>>> 2-PICK  (any sport, balanced)")
    for i, p in enumerate(build_parlays(df, sport=None, num_picks=2, n_parlays=3, mode="balanced")):
        print_parlay(p, i, 2, "balanced")

    active_sports = df["sport_id"].unique()

    if "NBA" in active_sports:
        print("\n>>> NBA 3-PICK  (balanced)")
        for i, p in enumerate(build_parlays(df, sport="NBA", num_picks=3, n_parlays=3, mode="balanced")):
            print_parlay(p, i, 3, "balanced")

    if "MLB" in active_sports:
        print("\n>>> MLB 3-PICK  (balanced)")
        for i, p in enumerate(build_parlays(df, sport="MLB", num_picks=3, n_parlays=3, mode="balanced")):
            print_parlay(p, i, 3, "balanced")

    mixed = [s for s in ["NBA", "MLB", "NHL"] if s in active_sports]
    if mixed:
        print(f"\n>>> MIXED 4-PICK  ({'+'.join(mixed)}, balanced)")
        for i, p in enumerate(build_parlays(df, sport=mixed, num_picks=4, n_parlays=3, mode="balanced")):
            print_parlay(p, i, 4, "balanced")

    print("\n>>> 5-PICK  (any sport, balanced)")
    for i, p in enumerate(build_parlays(df, sport=None, num_picks=5, n_parlays=3, mode="balanced")):
        print_parlay(p, i, 5, "balanced")

    # ── VALUE / HIGH-BOOST PARLAYS ──────────────────────────────────────────────
    print("\n\n" + "─"*65)
    print("  VALUE PARLAYS  (max payout_multiplier boost — higher risk!)")
    print("─"*65)

    print("\n>>> VALUE 3-PICK  (any sport)")
    for i, p in enumerate(build_parlays(df, sport=None, num_picks=3, n_parlays=2, mode="value")):
        print_parlay(p, i, 3, "value")

    print("\n>>> VALUE 4-PICK  (any sport)")
    for i, p in enumerate(build_parlays(df, sport=None, num_picks=4, n_parlays=2, mode="value")):
        print_parlay(p, i, 4, "value")

    print()
    print("─"*65)
    print("Boost [x1.00] = fair-value line. Higher = Underdog gives extra.")
    print("Power play: all picks must hit for full payout.")
    print("Flex play:  can miss 1 pick for reduced payout.")


if __name__ == "__main__":
    main()
