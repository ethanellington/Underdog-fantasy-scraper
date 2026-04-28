"""Build 3+ leg parlays from scraped Underdog Pick'em props.

Strategy:
- Run the existing UnderdogScraper to fetch live over/under lines.
- Dedupe each line to its best (highest implied probability) side.
- Group props per sport and assemble a few parlays:
    * "Safe" parlays  -> picks with the highest implied probability (favorites).
    * "Value" parlays -> moderate-probability picks with juicier prices.
    * "Longshot"      -> lower-probability picks with the highest combined payout.
- One pick per player to avoid correlated/duplicate legs in a parlay.
"""

from itertools import islice
import pandas as pd

from underdog_scraper import UnderdogScraper


def load_props() -> pd.DataFrame:
    s = UnderdogScraper()
    pickem = s.fetch_data()
    players, appearances, over_under_lines = s.combine_data(pickem)
    df = s.process_data(players, appearances, over_under_lines)
    df = df.loc[:, ~df.columns.duplicated()]
    df = df[df["status"] != "suspended"].copy()
    df["decimal_price"] = pd.to_numeric(df["decimal_price"], errors="coerce")
    df["stat_value"] = pd.to_numeric(df["stat_value"], errors="coerce")
    df = df.dropna(subset=["decimal_price", "full_name", "stat_name", "choice"])
    df["implied_prob"] = 1.0 / df["decimal_price"]
    return df


def best_side_per_line(df: pd.DataFrame) -> pd.DataFrame:
    """For each over/under line, keep the side with the higher implied probability."""
    df = df.sort_values("implied_prob", ascending=False)
    return df.drop_duplicates(subset=["over_under_line_id"], keep="first")


def assemble_parlay(pool: pd.DataFrame, n_legs: int) -> pd.DataFrame:
    """Pick n_legs from the pool, max one leg per player."""
    seen_players = set()
    legs = []
    for _, row in pool.iterrows():
        if row["full_name"] in seen_players:
            continue
        seen_players.add(row["full_name"])
        legs.append(row)
        if len(legs) == n_legs:
            break
    return pd.DataFrame(legs)


def fmt_parlay(name: str, legs: pd.DataFrame) -> str:
    if legs.empty:
        return f"{name}: not enough props available\n"
    combined_decimal = legs["decimal_price"].prod()
    combined_prob = legs["implied_prob"].prod()
    out = [f"=== {name} ({len(legs)} legs) ==="]
    for i, row in enumerate(legs.itertuples(index=False), 1):
        out.append(
            f"  {i}. [{row.sport_id}] {row.full_name:<28} "
            f"{row.choice.upper():<5} {row.stat_value:>5} {row.stat_name:<22} "
            f"@ {row.american_price:>5}  (p={row.implied_prob:.3f})"
        )
    payout_mult = combined_decimal  # standard parlay multiplier
    out.append(
        f"  >> combined implied prob = {combined_prob:.4f}  "
        f"|  parlay decimal odds = {combined_decimal:.2f}x  "
        f"|  $10 -> ${10 * payout_mult:.2f}"
    )
    return "\n".join(out) + "\n"


def main():
    df = load_props()
    df = best_side_per_line(df)

    sports_with_data = (
        df.groupby("sport_id")
        .size()
        .sort_values(ascending=False)
    )
    print("Available sports (line counts):")
    for sport, n in sports_with_data.items():
        print(f"  {sport:<10} {n}")
    print()

    parlays = []

    # 1) Top-confidence NBA 3-leg
    nba = df[df["sport_id"] == "NBA"].sort_values("implied_prob", ascending=False)
    parlays.append(("NBA Safe 3-Leg", assemble_parlay(nba, 3)))

    # 2) NBA 5-leg "power" parlay
    parlays.append(("NBA Safe 5-Leg", assemble_parlay(nba, 5)))

    # 3) MLB 4-leg favorites
    mlb = df[df["sport_id"] == "MLB"].sort_values("implied_prob", ascending=False)
    parlays.append(("MLB Safe 4-Leg", assemble_parlay(mlb, 4)))

    # 4) NHL 3-leg favorites
    nhl = df[df["sport_id"] == "NHL"].sort_values("implied_prob", ascending=False)
    parlays.append(("NHL Safe 3-Leg", assemble_parlay(nhl, 3)))

    # 5) Mixed-sport 4-leg favorites (one per sport)
    mixed_pool = (
        df.sort_values("implied_prob", ascending=False)
        .groupby("sport_id", as_index=False)
        .head(1)
        .sort_values("implied_prob", ascending=False)
    )
    parlays.append(("Mixed-Sport 4-Leg Favorites", assemble_parlay(mixed_pool, 4)))

    # 6) Value 3-leg (moderate probability, juicier price)
    value_pool = (
        df[(df["implied_prob"] >= 0.50) & (df["implied_prob"] <= 0.58)]
        .sort_values("decimal_price", ascending=False)
    )
    parlays.append(("Value 3-Leg (juicier prices)", assemble_parlay(value_pool, 3)))

    # 7) Longshot 3-leg (lower probability legs, big payout)
    longshot_pool = (
        df[df["implied_prob"] < 0.50]
        .sort_values("decimal_price", ascending=False)
    )
    parlays.append(("Longshot 3-Leg (high payout)", assemble_parlay(longshot_pool, 3)))

    for name, legs in parlays:
        print(fmt_parlay(name, legs))


if __name__ == "__main__":
    main()
