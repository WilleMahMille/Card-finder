# Card finder

## GitHub Repository

[https://github.com/WilleMahMille/card-finder](https://github.com/WilleMahMille/card-finder)

A collection of tools for managing Magic: The Gathering cards. Includes a web scraper, price optimizer (using dynamic programming), and a card trade-in matcher. Built for use with CardMarket and DragonsLair (Swedish board game store).

## Installation

Built for Python 3.12.9 and may not work with other versions. Each subfolder has its own `requirements.txt`:

```
pip install -r requirements.txt
```

For browser functionality (used by the CardMarket scraper), Playwright's browser binaries also need to be installed:

```
playwright install
```

## Subfolders

### CardMarket

Web scraper and price optimizer for [cardmarket.com](https://www.cardmarket.com). Gathers filtered listings for a set of desired cards (loaded from CSV files, Moxfield URLs, or decklists), then uses dynamic programming to find the cheapest combination of sellers accounting for shipping costs. Includes stealth measures against Cloudflare bot detection, automatic captcha handling, and a headless mode for automated use.

### DragonsLair

Scraper for [list.dragonslair.se](https://list.dragonslair.se) that finds all cards currently available for trade-in, and matches them against cards you own to calculate your total trade-in value. Includes an incremental scan runner for scheduled use via GitHub Actions, which runs on a cron schedule and stores results on a separate data branch.
