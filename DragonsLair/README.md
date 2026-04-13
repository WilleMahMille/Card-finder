## DragonsLair card trade-in matcher

## Description

An automatic scraper that finds all cards currently tradable in DragonsLair shops (list.dragonslair.se) and matches them with cards you own, telling you how much you can trade in your cards for. Useful if you want to trade duplicates or unused cards for store credit toward other singles.

## How it works

The scraper iterates through all card sets on the DragonsLair singles listing page to gather card names, prices, and buy-in information. Once the data is collected, it matches cards you specify against the tradable cards to calculate the total trade-in value. Owned cards can be exported from Manabox or any CSV with the required columns. Matching is currently based on card name, set name, and foil status.

## Usage

### Manual run

```
python main.py --owned-cards ./owned-cards.csv --output ./output.txt
```

Where `owned-cards.csv` is a CSV file with `Name`, `Set Name`, `Foil`, and `Quantity` columns. This will scrape all tradable cards and save them to `./tradable_cards.csv`.

To skip re-scraping and reuse previously gathered data:

```
python main.py --owned-cards ./owned-cards.csv --tradable-cards ./tradable_cards.csv --output ./output.txt
```

### Automated scanning (scan runner)

`scan_runner.py` is an incremental scanner designed for scheduled/CI use. It runs with a request budget per invocation (default 250), saves progress, and resumes where it left off on the next run. New sets are detected and prioritized automatically.

Configuration is via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `REQUEST_BUDGET` | 250 | Max HTTP requests per run |
| `MIN_SLEEP` / `MAX_SLEEP` | 2 / 8 | Random delay range between requests (seconds) |
| `COOLDOWN_DAYS` | 60 | Days to wait after a full scan before starting a new cycle |
| `FORCE_RUN` | 0 | Set to 1 to bypass cooldown |
| `SCAN_MODE` | resume | `resume`, `new-sets-only`, or `full-rescan` |

A GitHub Actions workflow (`.github/workflows/scan-dragonslair.yml`) runs the scanner 4 times per day on a cron schedule and commits results to a separate `data` branch. It can also be triggered manually via workflow dispatch.
