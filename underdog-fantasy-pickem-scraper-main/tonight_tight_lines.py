import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from underdog_scraper import UnderdogScraper
import pandas as pd
from datetime import datetime, timezone, timedelta


class TightLinesFinder(UnderdogScraper):
    def combine_data(self, pickem_data):
        players, appearances, over_under_lines = super().combine_data(pickem_data)
        games = pd.DataFrame(pickem_data.get("games", []))
        return players, appearances, over_under_lines, games

    def filter_tonight(self, df, games):
        if games.empty or "scheduled_at" not in games.columns or "match_id" not in df.columns:
            print("[WARNING] No game schedule data available — showing all live lines.\n")
            return df

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=24)
        games = games.copy()
        games["scheduled_at"] = pd.to_datetime(games["scheduled_at"], utc=True)
        tonight_ids = set(
            games[(games["scheduled_at"] >= now) & (games["scheduled_at"] <= cutoff)]["id"]
        )

        filtered = df[df["match_id"].isin(tonight_ids)]
        if filtered.empty:
            print("[WARNING] No games found in the next 24 hours — showing all live lines.\n")
            return df
        return filtered

    def find_tight_lines(self, df, top_n=25):
        over_df = df[df["choice"] == "over"].copy()
        over_df["decimal_price"] = pd.to_numeric(over_df["decimal_price"], errors="coerce")
        over_df = over_df.dropna(subset=["decimal_price"])
        over_df["implied_probability"] = 1 / over_df["decimal_price"]
        over_df["tight_score"] = (over_df["implied_probability"] - 0.5).abs()
        return over_df.sort_values("tight_score").head(top_n)

    def display(self, df):
        col_map = {
            "full_name": "Player",
            "sport_id": "Sport",
            "stat_name": "Stat",
            "stat_value": "Line",
            "implied_probability": "Over%",
            "american_price": "Odds",
            "tight_score": "Gap",
        }
        display_cols = [c for c in col_map if c in df.columns]
        out = df[display_cols].rename(columns=col_map).reset_index(drop=True)
        out.index += 1

        if "Over%" in out.columns:
            out["Over%"] = (out["Over%"] * 100).round(1).astype(str) + "%"
        if "Gap" in out.columns:
            out["Gap"] = (out["Gap"] * 100).round(1).astype(str) + "%"

        pd.set_option("display.max_rows", None)
        pd.set_option("display.max_colwidth", 30)
        pd.set_option("display.width", 120)
        print(out.to_string())

    def run(self, top_n=25):
        print("Fetching Underdog Fantasy lines...")
        raw = self.fetch_data()

        players, appearances, over_under_lines, games = self.combine_data(raw)
        processed = self.process_data(players, appearances, over_under_lines)
        processed = processed.reset_index(drop=True)
        processed = processed.loc[:, ~processed.columns.duplicated()]
        processed = processed[processed["status"] != "suspended"]

        tonight = self.filter_tonight(processed, games)
        tight = self.find_tight_lines(tonight, top_n=top_n)

        count = len(tight)
        print(f"\nTop {count} tightest lines for tonight:\n")
        self.display(tight)


if __name__ == "__main__":
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    TightLinesFinder().run(top_n=top_n)
