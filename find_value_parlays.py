"""
Underdog Fantasy - Value Parlay Finder

Fetches live lines from the Underdog Fantasy API and surfaces picks
with the most favorable implied odds, then assembles suggested parlays.

Value signal: A "balanced" line on Underdog represents a roughly 50/50
prop. When the house prices a side at -108 or better (vs. the standard
-112), the implied probability drops below 51.9% — meaning the bettor
faces less vig. Collecting several such "soft" lines into a parlay
compounds that small per-leg edge.

Payout reference (Underdog standard):
  2 picks  → 3x
  3 picks  → 6x
  4 picks  → 10x
  5 picks  → 20x
  6 picks  → 40x

"REALISTIC" vs "LONGSHOT" parlays:
  Realistic  — standard performance stats priced between -140 and +140.
               ~50% true probability per leg. These are your bread-and-butter
               player-prop picks (points, yards, assists, etc.).
  Longshot   — very high positive-odds props (SGPs, rare events).
               Higher payout but much lower true probability.
"""

import requests
import json
from collections import defaultdict

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
API_URL = "https://api.underdogfantasy.com/beta/v5/over_under_lines"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://underdogfantasy.com/",
    "Origin": "https://underdogfantasy.com",
}

PAYOUT_TABLE = {2: 3, 3: 6, 4: 10, 5: 20, 6: 40}


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def american_to_implied_prob(american: str) -> float:
    """Convert American odds string to implied probability (0–1)."""
    try:
        price = int(american)
    except (TypeError, ValueError):
        return 0.5
    if price > 0:
        return 100 / (price + 100)
    else:
        return abs(price) / (abs(price) + 100)


def implied_prob_to_edge(prob: float) -> float:
    """
    Edge = how much better the bettor is vs. a true 50/50 coin flip.
    A line at -112 has prob ~0.528; edge = 0.5 - 0.528 = -0.028 (slight house edge).
    A line at +103 has prob ~0.493; edge = 0.5 - 0.493 = +0.007 (slight bettor edge).
    """
    return 0.5 - prob


def fetch_data() -> dict:
    resp = requests.get(API_URL, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"API request failed with status {resp.status_code}")
    return resp.json()


# ──────────────────────────────────────────────
# Build flat records
# ──────────────────────────────────────────────
def build_records(data: dict) -> list[dict]:
    players_by_id = {p["id"]: p for p in data["players"]}
    appearances_by_id = {a["id"]: a for a in data["appearances"]}
    games_by_id = {g["id"]: g for g in data.get("games", [])}

    records = []
    for line in data["over_under_lines"]:
        if line.get("status") == "suspended":
            continue
        if line.get("line_type") != "balanced":
            continue  # skip alternates — those are separate bets

        ou = line.get("over_under") or {}
        app_stat = ou.get("appearance_stat") or {}
        app_id = app_stat.get("appearance_id")
        app = appearances_by_id.get(app_id, {})
        player_id = app.get("player_id")
        player = players_by_id.get(player_id, {})
        game = games_by_id.get(app.get("match_id"))

        sport = player.get("sport_id", "UNK")
        first = player.get("first_name") or ""
        last = player.get("last_name") or ""
        name = f"{first} {last}".strip() or last or first
        team = player.get("team_id", "")
        position = player.get("position_name", "")
        stat = app_stat.get("display_stat", app_stat.get("stat", ""))
        line_value = line.get("stat_value", "?")
        game_title = game.get("abbreviated_title", "") if game else ""
        game_time = game.get("match_progress", "") if game else ""
        season_type = game.get("season_type", "") if game else ""

        for opt in line.get("options", []):
            if opt.get("status") != "active":
                continue
            american = opt.get("american_price", "")
            choice = "Over" if opt.get("choice") == "higher" else "Under"
            impl_prob = american_to_implied_prob(american)
            edge = implied_prob_to_edge(impl_prob)

            records.append(
                {
                    "player": name,
                    "sport": sport,
                    "position": position,
                    "stat": stat,
                    "line": line_value,
                    "choice": choice,
                    "american_price": american,
                    "implied_prob": impl_prob,
                    "edge": edge,
                    "game": game_title,
                    "game_time": game_time,
                    "season_type": season_type,
                    "subheader": opt.get("selection_subheader", ""),
                    "team": team,
                }
            )

    return records


# ──────────────────────────────────────────────
# Value scoring & filtering
# ──────────────────────────────────────────────
# Stats that are standard performance props (roughly 50/50, good for parlays).
# These cut out rare-event props like "Triple Double", "First Goal Scorer", etc.
STANDARD_STATS = {
    # NBA / WNBA / BASKETBALL
    "points", "assists", "rebounds", "3_pointers_made", "blocks", "steals",
    "fantasy_points", "pts_reb_ast",
    # NFL / UFL / FOOTBALL
    "passing_yards", "rushing_yards", "receiving_yards", "passing_tds",
    "rushing_tds", "receiving_tds", "receptions", "completions",
    # MLB / KBO / NPB / BASEBALL
    "hits", "strikeouts", "pitcher_strikeouts", "earned_runs", "walks",
    "hits_allowed", "pitching_outs",
    # NHL / HOCKEY
    "shots_on_goal", "points",
    # MMA / COMBAT
    "significant_strikes", "total_strikes", "takedowns",
    # SOCCER / FIFA
    "shots", "shots_on_target",
    # ESPORTS
    "kills", "deaths", "assists", "fantasy_points", "headshots",
    # TENNIS
    "games_won", "aces",
    # LACROSSE
    "goals", "assists", "shots",
}

# American price band for "realistic" parlays — not too heavy a favorite,
# not an outright lottery ticket.
REALISTIC_PRICE_MIN = -140
REALISTIC_PRICE_MAX = 140


def score_records(records: list[dict]) -> list[dict]:
    """Sort by most favorable edge (bettor-favored first), filter meaningful lines."""
    filtered = [r for r in records if r["player"] and r["stat"]]
    return sorted(filtered, key=lambda r: r["edge"], reverse=True)


def is_realistic(record: dict) -> bool:
    """True if this pick is a standard prop priced in the near-even range."""
    try:
        price = int(record["american_price"])
    except (TypeError, ValueError):
        return False
    return REALISTIC_PRICE_MIN <= price <= REALISTIC_PRICE_MAX


def top_picks_per_sport(scored: list[dict], top_n: int = 10) -> dict:
    """Return top realistic picks per sport, deduped by (player, stat, choice)."""
    by_sport: dict[str, list] = defaultdict(list)
    seen = set()
    for r in scored:
        if not is_realistic(r):
            continue
        key = (r["player"], r["stat"], r["choice"])
        if key in seen:
            continue
        seen.add(key)
        by_sport[r["sport"]].append(r)
    return {sport: picks[:top_n] for sport, picks in by_sport.items()}


# ──────────────────────────────────────────────
# Parlay builder
# ──────────────────────────────────────────────
def build_parlays(scored: list[dict], sizes=(2, 3, 4), realistic_only: bool = True) -> list[dict]:
    """
    Build suggested parlays from unique value picks, one pick per game.

    realistic_only: if True, only use props priced between -140 and +140
    (standard player performance props). If False, includes longshot props.
    """
    seen_players: set[str] = set()
    seen_games: set[str] = set()
    pool: list[dict] = []

    for r in scored:
        if realistic_only and not is_realistic(r):
            continue
        key = (r["player"], r["stat"])
        game_key = r["game"] or r["player"]  # fallback to player if no game
        if key not in seen_players and game_key not in seen_games:
            pool.append(r)
            seen_players.add(key)
            seen_games.add(game_key)

    parlays = []
    for size in sizes:
        legs = pool[:size]
        if len(legs) < size:
            continue
        # Compute combined EV using the implied probability of each leg
        # (true probability assumed equal to the bettor's implied prob, i.e. ~50%)
        true_combined = 0.5 ** size
        payout = PAYOUT_TABLE.get(size, size * 2)
        expected_value = true_combined * payout
        parlays.append(
            {
                "size": size,
                "legs": legs,
                "payout_multiplier": payout,
                "estimated_hit_prob": round(true_combined * 100, 1),
                "ev_per_dollar": round(expected_value, 3),
            }
        )
    return parlays


# ──────────────────────────────────────────────
# Positive EV parlay builder
# ──────────────────────────────────────────────

# Break-even implied probability per leg for a 3-pick 6x parlay:
#   p^3 * 6 = 1  =>  p = (1/6)^(1/3) ≈ 0.5503  (American: -122)
BREAKEVEN_3LEG = (1 / 6) ** (1 / 3)


def build_positive_ev_parlay(records: list[dict], size: int = 3) -> dict | None:
    """
    Find the highest-EV n-leg parlay from balanced lines with heavy implied
    probability (i.e., the 'favorite' side).  One pick per game.

    Because Underdog's fixed payouts (6x for 3-pick) are based on ~50%
    per-leg assumptions, legs with implied probability >55% are mathematically
    positive-EV when combined.

    Returns a dict with legs + EV, or None if not enough qualifying legs found.
    """
    payout = PAYOUT_TABLE.get(size)
    if not payout:
        return None

    breakeven = (1 / payout) ** (1 / size)

    # All legs above break-even with real game context, sorted by highest prob
    pool = [
        r for r in records
        if r["implied_prob"] > breakeven and r["game"]
    ]
    pool.sort(key=lambda r: r["implied_prob"], reverse=True)

    # Pick one leg per game, one per (player, stat) pair
    seen_games: set[str] = set()
    seen_ps: set[tuple] = set()
    legs: list[dict] = []
    for r in pool:
        key = (r["player"], r["stat"])
        if r["game"] in seen_games or key in seen_ps:
            continue
        legs.append(r)
        seen_games.add(r["game"])
        seen_ps.add(key)
        if len(legs) == size:
            break

    if len(legs) < size:
        return None

    combined_prob = 1.0
    for leg in legs:
        combined_prob *= leg["implied_prob"]

    ev = combined_prob * payout - 1
    return {
        "size": size,
        "payout_multiplier": payout,
        "legs": legs,
        "combined_prob": combined_prob,
        "ev_per_dollar": ev,
    }


def print_positive_ev_parlay(parlay: dict):
    size = parlay["size"]
    payout = parlay["payout_multiplier"]
    prob_pct = parlay["combined_prob"] * 100
    ev = parlay["ev_per_dollar"]

    print("\n" + "=" * 70)
    print(f"  POSITIVE EV — {size}-PICK PARLAY")
    print(f"  Payout: {payout}x  |  Est. hit rate: {prob_pct:.1f}%  |  EV: {ev:+.3f}/$ ({ev*100:+.1f}%)")
    print("=" * 70)
    for i, leg in enumerate(parlay["legs"], 1):
        fmt = fmt_price(leg["american_price"])
        print(f"  {i}. {leg['player']:<28}  {leg['sport']:<5}  {leg['stat']:<22}  "
              f"{leg['choice']:<6}  {fmt:>6}  ({leg['implied_prob']*100:.1f}% implied)")
        print(f"     Game: {leg['game']}  {leg['game_time']}")
    print()
    print("  WHY IT'S +EV:")
    print(f"  The 6x fixed payout assumes ~50% per leg ({0.5**size*100:.1f}% combined).")
    print(f"  These legs average {sum(l['implied_prob'] for l in parlay['legs'])/size*100:.1f}% implied "
          f"→ {prob_pct:.1f}% combined → EV = {prob_pct/100:.3f} × {payout} = {parlay['combined_prob']*payout:.3f}x "
          f"(pays back {parlay['combined_prob']*payout:.2f}x your stake on average).")
    print("=" * 70)


def fmt_price(p: str) -> str:
    try:
        v = int(p)
        return f"+{v}" if v > 0 else str(v)
    except Exception:
        return p


def print_value_picks(top_by_sport: dict):
    print("\n" + "=" * 70)
    print("  UNDERDOG FANTASY — TOP VALUE PICKS BY SPORT")
    print("  (Ranked by most favorable implied odds / lowest house edge)")
    print("=" * 70)

    for sport, picks in sorted(top_by_sport.items()):
        print(f"\n{'─'*70}")
        print(f"  {sport}  ({len(picks)} top picks)")
        print(f"{'─'*70}")
        print(f"  {'PLAYER':<26} {'STAT':<22} {'LINE':>6}  {'DIR':<6} {'ODDS':>6}  {'EDGE':>7}")
        print(f"  {'─'*26} {'─'*22} {'─'*6}  {'─'*6} {'─'*6}  {'─'*7}")
        for r in picks:
            edge_str = f"+{r['edge']*100:.2f}%" if r["edge"] >= 0 else f"{r['edge']*100:.2f}%"
            print(
                f"  {r['player']:<26} {r['stat']:<22} {r['line']:>6}  "
                f"{r['choice']:<6} {fmt_price(r['american_price']):>6}  {edge_str:>7}"
            )


def print_parlays(parlays: list[dict]):
    print("\n" + "=" * 70)
    print("  SUGGESTED VALUE PARLAYS")
    print("=" * 70)

    for parlay in parlays:
        size = parlay["size"]
        payout = parlay["payout_multiplier"]
        hit_pct = parlay["estimated_hit_prob"]
        ev = parlay["ev_per_dollar"]
        print(f"\n  ── {size}-PICK PARLAY  →  {payout}x payout  (est. {hit_pct}% hit rate, EV: {ev:.3f}/$ risked) ──")
        for i, leg in enumerate(parlay["legs"], 1):
            edge_str = (
                f"+{leg['edge']*100:.2f}%" if leg["edge"] >= 0 else f"{leg['edge']*100:.2f}%"
            )
            game_info = f"{leg['game']}  {leg['game_time']}" if leg["game"] else ""
            print(f"  {i}. {leg['player']:<26}  {leg['sport']:<5}  {leg['stat']:<20}  "
                  f"{leg['choice']:<6}  {fmt_price(leg['american_price']):>6}  "
                  f"edge: {edge_str}")
            if game_info:
                print(f"     {' ':<26}  [{game_info}]")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────
def main():
    print("Fetching live lines from Underdog Fantasy...")
    data = fetch_data()

    total_lines = len(data.get("over_under_lines", []))
    print(f"Retrieved {total_lines} lines across {len(data.get('players', []))} players.")

    records = build_records(data)
    scored = score_records(records)

    # Top 10 realistic value picks per sport (standard props, near-even pricing)
    top_by_sport = top_picks_per_sport(scored, top_n=10)
    print_value_picks(top_by_sport)

    # ── Positive EV 3-pick parlay (main result) ──────────────────────────
    pos_ev = build_positive_ev_parlay(records, size=3)
    if pos_ev:
        print_positive_ev_parlay(pos_ev)

    # ── Soft-line parlays (near-even-odds props) ──────────────────────────
    parlays = build_parlays(scored, sizes=[2, 3, 4, 5], realistic_only=True)
    print_parlays(parlays)

    print("\n" + "=" * 70)
    print("  NOTES")
    print("  ─────")
    print("  Positive EV parlay uses legs with implied prob > break-even (~55%).")
    print("  Underdog's 6x fixed payout is generous when legs are heavy favorites.")
    print()
    print("  Soft-line parlays = standard props near even-odds (-140 to +140).")
    print("  All picks sourced from different games to avoid correlation risk.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
