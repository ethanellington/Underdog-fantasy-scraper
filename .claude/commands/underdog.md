# Underdog Fantasy Props

Fetch live player props from Underdog Fantasy and analyze them.

**Arguments:** `$ARGUMENTS`

## Steps

### 1 — Scrape fresh data

Run this from the repo root to pull the latest props from the Underdog Fantasy API:

```bash
cd underdog-fantasy-pickem-scraper-main && python -c "from underdog_scraper import UnderdogScraper; UnderdogScraper().scrape()"
```

If it prints `Data saved to underdog_props.csv`, proceed. If it errors, report the error to the user.

### 2 — Analyze

Run the analysis script with the user's arguments:

```bash
cd underdog-fantasy-pickem-scraper-main && python underdog_analyze.py $ARGUMENTS
```

### 3 — Present results

Show the full output. Then add a short plain-English summary highlighting:
- Which sports / stat types have the most props right now
- Any notable or high-line props visible in the data
- Tips for next steps (e.g. "use `--sport NBA --stat points` to drill into NBA points props")

---

## Argument reference

| Flag | What it does | Example |
|------|--------------|---------|
| *(none)* | Full summary: sport breakdown, stat breakdown, sample props | `/underdog` |
| `--player NAME` | Profile for one player (partial name OK) | `--player "Mahomes"` |
| `--sport SPORT` | Filter to a sport | `--sport NBA` |
| `--stat STAT` | Filter by stat type (partial) | `--stat "points"` |
| `--team TEAM` | Filter by team abbreviation | `--team LAL` |
| `--position POS` | Filter by position | `--position QB` |
| `--choice over\|under` | Only show overs or unders | `--choice over` |
| `--min-line N` | Props with line ≥ N | `--min-line 30` |
| `--max-line N` | Props with line ≤ N | `--max-line 1.5` |
| `--top N` | Max rows shown (default 50) | `--top 20` |
| `--export FILE` | Save filtered results to CSV | `--export nba.csv` |
| `--format csv` | Output as raw CSV instead of table | `--format csv` |
| `--list-sports` | List all sports in today's slate | |
| `--list-stats` | List all stat types grouped by sport | |
| `--list-teams` | List all teams grouped by sport | |

## Quick-start examples

```
/underdog                                        # today's full slate summary
/underdog --list-sports                          # what sports are live right now
/underdog --list-stats                           # all available prop types
/underdog --sport NBA                            # all NBA props
/underdog --sport NBA --stat points --top 20     # top 20 NBA points props
/underdog --player "LeBron"                      # LeBron's props
/underdog --position QB                          # all QB props
/underdog --choice over --min-line 30            # high-value overs
/underdog --sport NFL --export nfl_props.csv     # dump NFL props to file
/underdog --sport MLB --stat "hits" --choice over --top 10   # MLB hits overs
```
