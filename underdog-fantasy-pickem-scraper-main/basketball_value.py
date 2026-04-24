import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from underdog_scraper import UnderdogScraper
import pandas as pd

STANDARD_STATS = {
    "points", "rebounds", "assists", "three_points_made", "pts_rebs_asts",
    "rebs_asts", "pts_rebs", "pts_asts", "steals", "blocks", "turnovers",
    "blks_stls", "period_1_points", "period_1_rebounds", "period_1_assists",
}

STAT_LABELS = {
    "points": "PTS", "rebounds": "REB", "assists": "AST",
    "three_points_made": "3PM", "pts_rebs_asts": "PRA",
    "rebs_asts": "RA", "pts_rebs": "PR", "pts_asts": "PA",
    "steals": "STL", "blocks": "BLK", "turnovers": "TO",
    "blks_stls": "BLK+STL", "period_1_points": "Q1 PTS",
    "period_1_rebounds": "Q1 REB", "period_1_assists": "Q1 AST",
}


def load_nba_props(min_implied_prob=0.25):
    s = UnderdogScraper()
    raw = s.fetch_data()
    players, appearances, ou = s.combine_data(raw)
    df = s.process_data(players, appearances, ou)
    df = df.reset_index(drop=True).loc[:, ~df.columns.duplicated()]
    df = df[df["status"] != "suspended"]

    nba = df[df["sport_id"] == "NBA"]
    over = nba[nba["choice"] == "over"].copy()

    over["payout_multiplier"] = pd.to_numeric(over["payout_multiplier"], errors="coerce")
    over["decimal_price"] = pd.to_numeric(over["decimal_price"], errors="coerce")
    over["implied_prob"] = 1 / over["decimal_price"]

    value = over[
        (over["payout_multiplier"] > 1.0)
        & (over["implied_prob"] >= min_implied_prob)
        & (over["stat_name"].isin(STANDARD_STATS))
    ].copy()

    value["stat_label"] = value["stat_name"].map(STAT_LABELS).fillna(value["stat_name"])
    value = value.sort_values("payout_multiplier", ascending=False)
    return value


def display(df, top_n=30):
    cols = ["full_name", "stat_label", "stat_value", "american_price", "payout_multiplier", "implied_prob"]
    cols = [c for c in cols if c in df.columns]
    out = df[cols].head(top_n).reset_index(drop=True)
    out.index += 1
    out = out.rename(columns={
        "full_name": "Player",
        "stat_label": "Stat",
        "stat_value": "Line",
        "american_price": "Odds",
        "payout_multiplier": "Boost",
        "implied_prob": "Hit%",
    })
    out["Hit%"] = (out["Hit%"] * 100).round(1).astype(str) + "%"
    out["Boost"] = out["Boost"].round(2).astype(str) + "x"

    pd.set_option("display.max_rows", None)
    pd.set_option("display.max_colwidth", 28)
    pd.set_option("display.width", 110)
    print(out.to_string())


if __name__ == "__main__":
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    min_prob = float(sys.argv[2]) if len(sys.argv) > 2 else 0.25

    print("Fetching NBA props...")
    props = load_nba_props(min_implied_prob=min_prob)
    print(f"\nTop {min(top_n, len(props))} best-value NBA props "
          f"(payout boost > 1x, implied hit rate >= {min_prob*100:.0f}%):\n")
    display(props, top_n=top_n)
