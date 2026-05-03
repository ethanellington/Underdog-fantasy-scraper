"""
TOR @ CLE parlay builder — pulls live Underdog lines and prints recommended picks.
"""
import requests
import json
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "underdog-fantasy-pickem-scraper-main", "config.json")
GAME_ID = 169374  # TOR @ CLE
TOR_TEAM = "fd41e35e-7b5d-48c3-be0c-69e958976f6b"
CLE_TEAM = "56fcd081-3e21-406e-af95-5716abbfba2e"


def fetch_props():
    config = json.load(open(CONFIG_PATH))
    data = requests.get(config["ud_pickem_url"], headers=config["headers"]).json()

    appearances = {r["id"]: r for r in data["appearances"] if r["match_id"] == GAME_ID}
    players = {r["id"]: r for r in data["players"] if r["id"] in {a["player_id"] for a in appearances.values()}}

    rows = []
    for line in data["over_under_lines"]:
        app_id = line["over_under"]["appearance_stat"]["appearance_id"]
        if app_id not in appearances:
            continue
        stat = line["over_under"]["appearance_stat"]["stat"]
        stat_value = line["stat_value"]
        pid = appearances[app_id]["player_id"]
        p = players.get(pid, {})
        name = p.get("first_name", "?") + " " + p.get("last_name", "?")
        team = "TOR" if appearances[app_id]["team_id"] == TOR_TEAM else "CLE"
        for opt in line.get("options", []):
            choice = {"lower": "under", "higher": "over"}.get(opt["choice"], opt["choice"])
            rows.append({"name": name, "team": team, "stat": stat,
                         "line": stat_value, "choice": choice,
                         "mult": float(opt.get("payout_multiplier") or 1.0)})
    return rows


def build_parlay(rows):
    lookup = {(r["name"], r["stat"], r["choice"]): r for r in rows}

    picks = [
        ("Jarrett Allen",  "double_doubles",       "over"),
        ("James Harden",   "double_doubles",       "over"),
        ("Evan Mobley",    "double_doubles",       "over"),
        ("Scottie Barnes", "rebounds",             "over"),
        ("RJ Barrett",     "three_points_made",    "over"),
    ]

    print("\n" + "=" * 65)
    print("  TOR @ CLE  —  RECOMMENDED 5-PICK POWER PLAY")
    print("=" * 65)
    combined = 1.0
    for name, stat, choice in picks:
        row = lookup.get((name, stat, choice))
        if not row:
            print(f"  [MISSING] {name} {stat} {choice}")
            continue
        combined *= row["mult"]
        print(f"  {'[' + row['team'] + ']':6s} {name:22s}  {stat} {choice.upper()} {row['line']}  x{row['mult']:.2f}")
    print("-" * 65)
    print(f"  Combined multiplier: x{combined:.2f}")
    print(f"  $10 entry  →  ${10 * combined:.2f}")
    print("=" * 65)

    print("\nRATIONALE")
    print("  Jarrett Allen  DD 0.5 (1.70x) — averaging 14 pts / 12 reb this postseason")
    print("  James Harden   DD 0.5 (2.15x) — best value; ~19 pts / 9 ast combo")
    print("  Evan Mobley    DD 0.5 (1.10x) — consistent 17 pts / 9 reb base")
    print("  Scottie Barnes reb 7.5 (1.08x) — TOR's engine, elite rebounder")
    print("  RJ Barrett     3PM 2.5 (1.10x) — expanded shooter, 3+ makes in range")
    print()


if __name__ == "__main__":
    rows = fetch_props()
    build_parlay(rows)
