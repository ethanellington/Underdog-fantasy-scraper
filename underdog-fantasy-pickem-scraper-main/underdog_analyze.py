"""
Analyze the underdog_props.csv produced by UnderdogScraper.

Usage:
    python underdog_analyze.py [options]

Run `python underdog_analyze.py --help` for full option list.
"""

import argparse
import os
import sys

import pandas as pd


CSV_PATH = os.path.join(os.path.dirname(__file__), "underdog_props.csv")

# ── helpers ──────────────────────────────────────────────────────────────────

def load(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        print(
            f"[error] {path} not found.\n"
            "Run the scraper first:\n"
            "  python -c \"from underdog_scraper import UnderdogScraper; "
            "UnderdogScraper().scrape()\"",
            file=sys.stderr,
        )
        sys.exit(1)
    df = pd.read_csv(path, low_memory=False)
    # Normalise the line column to numeric
    if "line" in df.columns:
        df["line"] = pd.to_numeric(df["line"], errors="coerce")
    return df


def _col(df: pd.DataFrame, *names: str) -> str | None:
    """Return the first column name that exists in df."""
    for n in names:
        if n in df.columns:
            return n
    return None


def sport_col(df: pd.DataFrame) -> str | None:
    return _col(df, "sport_id", "sport")


def stat_col(df: pd.DataFrame) -> str | None:
    return _col(df, "stat_name", "stat")


def name_col(df: pd.DataFrame) -> str | None:
    return _col(df, "full_name", "name")


def team_col(df: pd.DataFrame) -> str | None:
    return _col(df, "team_id", "team")


def pos_col(df: pd.DataFrame) -> str | None:
    return _col(df, "position_id", "position")


# ── filtering ─────────────────────────────────────────────────────────────────

def apply_filters(df: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    if args.player:
        nc = name_col(df)
        if nc:
            df = df[df[nc].str.contains(args.player, case=False, na=False)]

    if args.sport:
        sc = sport_col(df)
        if sc:
            df = df[df[sc].str.upper() == args.sport.upper()]

    if args.stat:
        stc = stat_col(df)
        if stc:
            df = df[df[stc].str.contains(args.stat, case=False, na=False)]

    if args.team:
        tc = team_col(df)
        if tc:
            df = df[df[tc].str.upper() == args.team.upper()]

    if args.position:
        pc = pos_col(df)
        if pc:
            df = df[df[pc].str.upper() == args.position.upper()]

    if args.choice:
        if "choice" in df.columns:
            df = df[df["choice"].str.lower() == args.choice.lower()]

    if args.min_line is not None and "line" in df.columns:
        df = df[df["line"] >= args.min_line]

    if args.max_line is not None and "line" in df.columns:
        df = df[df["line"] <= args.max_line]

    return df


# ── display helpers ────────────────────────────────────────────────────────────

def _pct(n: int, total: int) -> str:
    return f"{n / total * 100:.1f}%" if total else "0.0%"


def _table(df: pd.DataFrame, columns: list[str], max_rows: int = 50) -> str:
    cols = [c for c in columns if c in df.columns]
    if not cols:
        return "(no columns to display)"
    sub = df[cols].head(max_rows)
    return sub.to_string(index=False)


def print_summary(df: pd.DataFrame, top: int) -> None:
    total = len(df)
    print(f"\n{'━' * 60}")
    print(f"  UNDERDOG FANTASY — LIVE PROPS SUMMARY")
    print(f"{'━' * 60}")
    print(f"  Total props (rows): {total:,}")

    # ── by sport ──
    sc = sport_col(df)
    if sc:
        print(f"\n  Props by sport:")
        for sport, count in df[sc].value_counts().items():
            print(f"    {sport:<10} {count:>5}  ({_pct(count, total)})")

    # ── by stat ──
    stc = stat_col(df)
    if stc:
        print(f"\n  Props by stat type:")
        for stat, count in df[stc].value_counts().head(15).items():
            print(f"    {str(stat):<30} {count:>5}  ({_pct(count, total)})")

    # ── by choice ──
    if "choice" in df.columns:
        print(f"\n  Over / Under split:")
        for choice, count in df["choice"].value_counts().items():
            print(f"    {str(choice):<10} {count:>5}  ({_pct(count, total)})")

    # ── line distribution ──
    if "line" in df.columns and df["line"].notna().any():
        lines = df["line"].dropna()
        print(f"\n  Line value stats:")
        print(f"    min    {lines.min():.2f}")
        print(f"    median {lines.median():.2f}")
        print(f"    mean   {lines.mean():.2f}")
        print(f"    max    {lines.max():.2f}")

    # ── top players ──
    nc = name_col(df)
    if nc:
        print(f"\n  Players with most props:")
        for player, count in df[nc].value_counts().head(10).items():
            print(f"    {str(player):<30} {count:>3} props")

    # ── sample rows ──
    display_cols = [
        c for c in [
            "full_name", "position_id", "team_id", "sport_id",
            "stat_name", "line", "choice",
        ]
        if c in df.columns
    ]
    print(f"\n{'─' * 60}")
    print(f"  Sample props (first {min(top, total)}):")
    print(f"{'─' * 60}")
    print(_table(df, display_cols, max_rows=top))
    print(f"{'━' * 60}\n")


def print_filtered(df: pd.DataFrame, top: int, fmt: str) -> None:
    total = len(df)
    display_cols = [
        c for c in [
            "full_name", "position_id", "team_id", "sport_id",
            "stat_name", "line", "choice",
        ]
        if c in df.columns
    ]

    if fmt == "csv":
        cols = [c for c in display_cols if c in df.columns]
        print(df[cols].head(top).to_csv(index=False))
    else:
        print(f"\n  Showing {min(top, total)} of {total} matching props:\n")
        print(_table(df, display_cols, max_rows=top))
        print()


# ── info commands ─────────────────────────────────────────────────────────────

def list_sports(df: pd.DataFrame) -> None:
    sc = sport_col(df)
    if not sc:
        print("Sport column not found.")
        return
    print("\nAvailable sports:")
    for sport, count in df[sc].value_counts().items():
        print(f"  {sport:<12} {count:>5} props")
    print()


def list_stats(df: pd.DataFrame) -> None:
    stc = stat_col(df)
    if not stc:
        print("Stat column not found.")
        return
    sc = sport_col(df)
    print("\nAvailable stat types:")
    if sc:
        for sport in sorted(df[sc].dropna().unique()):
            stats = df[df[sc] == sport][stc].value_counts()
            print(f"\n  {sport}:")
            for stat, count in stats.items():
                print(f"    {str(stat):<35} {count:>4} props")
    else:
        for stat, count in df[stc].value_counts().items():
            print(f"  {str(stat):<35} {count:>4} props")
    print()


def list_teams(df: pd.DataFrame) -> None:
    tc = team_col(df)
    sc = sport_col(df)
    if not tc:
        print("Team column not found.")
        return
    print("\nAvailable teams:")
    if sc:
        for sport in sorted(df[sc].dropna().unique()):
            teams = df[df[sc] == sport][tc].value_counts()
            print(f"\n  {sport}: {', '.join(str(t) for t in teams.index)}")
    else:
        for team, count in df[tc].value_counts().items():
            print(f"  {str(team):<10} {count:>4} props")
    print()


def player_profile(df: pd.DataFrame, name: str) -> None:
    nc = name_col(df)
    if not nc:
        print("Name column not found.")
        return
    rows = df[df[nc].str.contains(name, case=False, na=False)]
    if rows.empty:
        print(f"\nNo props found for '{name}'.")
        return

    matches = rows[nc].unique()
    for player in matches:
        player_rows = rows[rows[nc] == player]
        print(f"\n{'─' * 50}")
        print(f"  {player}")
        extra = []
        for col in ["position_id", "team_id", "sport_id"]:
            if col in player_rows.columns:
                val = player_rows[col].dropna().iloc[0] if not player_rows[col].dropna().empty else "?"
                extra.append(str(val))
        if extra:
            print(f"  {' | '.join(extra)}")
        print()

        display_cols = [c for c in ["stat_name", "line", "choice"] if c in player_rows.columns]
        print(player_rows[display_cols].to_string(index=False))
    print()


# ── main ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="underdog_analyze",
        description="Analyze Underdog Fantasy props from underdog_props.csv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python underdog_analyze.py
  python underdog_analyze.py --sport NBA --stat points --top 20
  python underdog_analyze.py --player "Mahomes"
  python underdog_analyze.py --list-sports
  python underdog_analyze.py --list-stats
  python underdog_analyze.py --list-teams
  python underdog_analyze.py --min-line 30 --choice over
  python underdog_analyze.py --sport NFL --export nfl_props.csv
""",
    )

    # info commands
    p.add_argument("--list-sports", action="store_true", help="List all available sports")
    p.add_argument("--list-stats", action="store_true", help="List all stat types by sport")
    p.add_argument("--list-teams", action="store_true", help="List all teams by sport")

    # filters
    p.add_argument("--player", metavar="NAME", help="Filter by player name (partial, case-insensitive)")
    p.add_argument("--sport", metavar="SPORT", help="Filter by sport ID (e.g. NBA, NFL, MLB)")
    p.add_argument("--stat", metavar="STAT", help="Filter by stat type (partial, case-insensitive)")
    p.add_argument("--team", metavar="TEAM", help="Filter by team abbreviation")
    p.add_argument("--position", metavar="POS", help="Filter by position (e.g. QB, PG, SP)")
    p.add_argument("--choice", metavar="over|under", help="Show only over or under lines")
    p.add_argument("--min-line", type=float, metavar="N", help="Only props with line ≥ N")
    p.add_argument("--max-line", type=float, metavar="N", help="Only props with line ≤ N")

    # output control
    p.add_argument("--top", type=int, default=50, metavar="N", help="Max rows to display (default: 50)")
    p.add_argument("--export", metavar="FILE", help="Export filtered results to a CSV file")
    p.add_argument("--format", choices=["table", "csv"], default="table", help="Output format (default: table)")
    p.add_argument("--csv-path", metavar="PATH", default=CSV_PATH, help="Path to underdog_props.csv")

    return p


def main() -> None:
    args = build_parser().parse_args()
    df = load(args.csv_path)

    any_filter = any([
        args.player, args.sport, args.stat, args.team,
        args.position, args.choice,
        args.min_line is not None, args.max_line is not None,
    ])

    # ── info-only commands ────────────────────────────────────────────────────
    if args.list_sports:
        list_sports(df)
        return
    if args.list_stats:
        list_stats(df)
        return
    if args.list_teams:
        list_teams(df)
        return

    # ── player profile shortcut ───────────────────────────────────────────────
    if args.player and not any([args.sport, args.stat, args.team, args.position, args.choice,
                                 args.min_line is not None, args.max_line is not None]):
        player_profile(df, args.player)
        if args.export:
            nc = name_col(df)
            if nc:
                sub = df[df[nc].str.contains(args.player, case=False, na=False)]
                sub.to_csv(args.export, index=False)
                print(f"Exported {len(sub)} rows → {args.export}")
        return

    # ── apply filters ─────────────────────────────────────────────────────────
    filtered = apply_filters(df, args)

    if args.export:
        filtered.to_csv(args.export, index=False)
        print(f"Exported {len(filtered)} rows → {args.export}")

    if not any_filter:
        print_summary(df, top=args.top)
    else:
        print_filtered(filtered, top=args.top, fmt=args.format)


if __name__ == "__main__":
    main()
