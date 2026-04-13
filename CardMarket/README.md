# CardMarket web scraper and price optimizer

## Description

A web scraper for automatically gathering listings from the CardMarket website, combined with a dynamic programming optimizer that finds the cheapest way to buy a set of desired cards across multiple sellers (accounting for shipping costs).

Since CardMarket uses Cloudflare's anti-bot system, the scraper includes stealth measures (playwright-stealth, human-like delays and mouse movement) and automatic captcha detection. It works well for up to ~100 cards at a time, but repeated heavy use will trigger increasingly aggressive blocking.

## Features

- **Multiple card sources** — load from CSV files, Moxfield deck URLs, or standard decklist files
- **Interactive card editor** — curses-based terminal editor for managing card lists
- **Automatic and manual gathering modes** — let the bot scrape for you or browse manually while it collects data in the background
- **Headless mode** — run the browser without a visible window for automated/CI use
- **Captcha handling** — detects Cloudflare challenges and pauses for manual solving (or errors out in headless mode)
- **Price optimization** — finds the cheapest combination of sellers using dynamic programming, factoring in per-seller shipping costs

## How it works

Running `python main.py` without arguments starts an interactive menu with the following options:

1. **Load / Manage Cards** — select a CSV from `Resources/DesiredCards/`, import from a Moxfield URL or decklist file, or edit cards interactively
2. **Manage Listings** — load previously saved listings, view stats, or clear current data
3. **Gather Listings** — scrape CardMarket for the loaded cards (automatic or manual mode)
4. **Find Cheapest** — run the optimizer on gathered listings
5. **Settings** — change target country, language, etc.

### Automatic mode

The program browses CardMarket for you and collects filtered listings. Cloudflare may present a captcha after some time — the program detects this and pauses until you solve it in the browser window (or raises an error in headless mode).

### Manual mode

You browse CardMarket yourself while the program automatically scrapes listings from every page you visit. This avoids bot detection entirely but is slower.

## Usage

### Basic usage (interactive)

```
python main.py
```

### CLI usage

All available flags:

```
python main.py -h
```

Common examples:

```bash
# Gather listings for a card list
python main.py --cards Resources/DesiredCards/default.csv --gather

# Import from a Moxfield deck and gather
python main.py --moxfield https://www.moxfield.com/decks/abc123 --gather

# Import from a decklist file
python main.py --decklist my_deck.txt --gather

# Run headless (no browser window)
python main.py --cards Resources/DesiredCards/default.csv --gather --headless

# Find cheapest using previously gathered listings
python main.py --cards Resources/DesiredCards/default.csv --listings Resources/Listings/listings_df_20260121.out.csv --find-cheapest

# Full pipeline: gather + optimize + write results
python main.py --cards Resources/DesiredCards/default.csv --gather --find-cheapest --output ./output.txt
```

### Card list format

Card lists are CSV files stored in `Resources/DesiredCards/`. They should have a `card_name` column (or a single unnamed column) with one card name per row.

### Advanced usage

#### Filtering

Listing filtering on CardMarket is done through URL parameters in the `_modify_url` method of `CardApi`. To customize which listings are shown (e.g. by condition, seller type, or language), modify this method.

#### Shipping prices

The `ShippingApi` class scrapes shipping cost tiers from CardMarket by country. To adjust the maximum card value considered for shipping tiers, change `SHIPPING_MAX_VALUE`. The shipping data is cached to `shipping_dict.json` after the first fetch.
