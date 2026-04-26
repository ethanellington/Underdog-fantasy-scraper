"""NBA prop value finder using the Underdog Pickem snapshot.

Limits of this data source:
- Underdog Pickem props only — no ML/spread/total, no multi-book, no line history,
  no public betting %, no reverse-line-movement signal.
- Each line has a payout multiplier per side. The side with the *lower* multiplier
  is the demoted/safer side (book's view of the more-likely outcome).

Two cross-checking signals are produced per line:
  fav_mult   — the lower of (over_mult, under_mult); rough proxy for confidence
  fav_devig  — devigged American-price implied probability of the favored side

Plays are surfaced where both signals agree the favored side has >= ~65% probability.
"""

import sys
from datetime import datetime, timezone, timedelta
import pandas as pd
from underdog_scraper import UnderdogScraper


def amer_to_prob(a):
    if pd.isna(a):
        return None
    a = float(a)
    return abs(a) / (abs(a) + 100) if a < 0 else 100 / (a + 100)


def load_today_props(et_date_str=None):
    """Pull tonight's NBA prop board. et_date_str = 'YYYY-MM-DD' in US-Eastern; default = today UTC -> ET window."""
    s = UnderdogScraper()
    data = s.fetch_data()
    players, appearances, ouls = s.combine_data(data)
    processed = s.process_data(players, appearances, ouls)
    processed = processed.loc[:, ~processed.columns.duplicated()]
    df = processed[processed["status"] != "suspended"].copy()
    df["match_id_int"] = df["match_id"].astype("Int64")
    df["payout_multiplier"] = pd.to_numeric(df["payout_multiplier"], errors="coerce")
    df["stat_value"] = pd.to_numeric(df["stat_value"], errors="coerce")
    df["american_price"] = pd.to_numeric(df["american_price"], errors="coerce")

    games = pd.DataFrame(data["games"])
    games["scheduled_dt"] = pd.to_datetime(games["scheduled_at"])
    if et_date_str:
        d = datetime.strptime(et_date_str, "%Y-%m-%d")
    else:
        d = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=-4)))
    start = pd.Timestamp(f"{d.strftime('%Y-%m-%d')}T04:00:00Z")
    end = start + pd.Timedelta(days=1)
    nba_today = games[(games["sport_id"] == "NBA") & (games["scheduled_dt"] >= start) & (games["scheduled_dt"] < end)]

    today_ids = set(nba_today["id"].astype(int).tolist())
    mid_to_title = dict(zip(games["id"], games["short_title"]))
    today = df[(df["sport_id"] == "NBA") & (df["match_id_int"].isin(today_ids))].copy()
    today["game"] = today["match_id_int"].map(mid_to_title)
    today = today[~today["stat_name"].str.startswith("period_")]
    today = today[today["stat_name"] != "fantasy_points"]
    return today, nba_today


def build_signal_table(today):
    pv = today.pivot_table(
        index=["game", "full_name", "stat_name", "stat_value"],
        columns="choice",
        values=["payout_multiplier", "american_price"],
        aggfunc="first",
    ).reset_index()
    pv.columns = ["_".join([c for c in col if c]).strip("_") for col in pv.columns.values]
    pv = pv.rename(
        columns={
            "payout_multiplier_over": "over_m",
            "payout_multiplier_under": "under_m",
            "american_price_over": "over_p",
            "american_price_under": "under_p",
        }
    )
    for c in ("over_m", "under_m"):
        pv[c] = pd.to_numeric(pv[c], errors="coerce")
    pv["over_implied"] = pv["over_p"].apply(amer_to_prob)
    pv["under_implied"] = pv["under_p"].apply(amer_to_prob)
    tot = pv["over_implied"] + pv["under_implied"]
    pv["over_devig"] = pv["over_implied"] / tot
    pv["under_devig"] = pv["under_implied"] / tot

    pv["fav_side"] = ""
    pv.loc[pv["over_m"] < pv["under_m"], "fav_side"] = "OVER"
    pv.loc[pv["under_m"] < pv["over_m"], "fav_side"] = "UNDER"
    pv["fav_mult"] = pv[["over_m", "under_m"]].min(axis=1)
    pv["fav_devig"] = pv.apply(
        lambda r: r["over_devig"] if r["fav_side"] == "OVER" else (r["under_devig"] if r["fav_side"] == "UNDER" else None),
        axis=1,
    )
    return pv


if __name__ == "__main__":
    today, slate = load_today_props(sys.argv[1] if len(sys.argv) > 1 else None)
    print("Slate:")
    print(slate[["short_title", "scheduled_at"]].to_string(index=False))
    pv = build_signal_table(today)
    plays = pv[(pv["fav_side"] != "") & (pv["fav_mult"] <= 0.72) & (pv["fav_devig"] >= 0.65)].sort_values("fav_mult")
    print("\nStrong plays (fav_mult <= 0.72 AND devig >= 65%):")
    print(plays[["game", "full_name", "stat_name", "stat_value", "fav_side", "fav_mult", "fav_devig"]].to_string(index=False))
