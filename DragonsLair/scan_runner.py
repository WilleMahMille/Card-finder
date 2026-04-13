"""
Incremental scan runner for Dragons Lair card data.

Runs with a request budget per run (default 250), saves progress to a data branch,
and resumes where it left off on the next run. New sets are detected and prioritized.

After a full scan completes, the scanner pauses for a cooldown period (default 60 days)
before starting a new cycle. Manual dispatch (FORCE_RUN=1) bypasses the cooldown.
"""

import json
import os
import random
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd
import requests

from scraper import BASE_URL, find_tradable_cards, get_sets

DATA_DIR = Path("data")
PROGRESS_FILE = DATA_DIR / "progress.json"
CARDS_FILE = DATA_DIR / "tradable_cards.csv"
REQUEST_BUDGET = int(os.environ.get("REQUEST_BUDGET", "250"))
MIN_SLEEP = float(os.environ.get("MIN_SLEEP", "2"))
MAX_SLEEP = float(os.environ.get("MAX_SLEEP", "8"))
COOLDOWN_DAYS = int(os.environ.get("COOLDOWN_DAYS", "60"))
FORCE_RUN = os.environ.get("FORCE_RUN", "0") == "1"
SCAN_MODE = os.environ.get("SCAN_MODE", "resume")  # resume | new-sets-only | full-rescan


def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {
        "scanned_sets": {},
        "queue": [],
        "last_run": None,
        "known_sets": [],
        "requests_today": 0,
        "scan_completed_at": None,
    }


def save_progress(progress):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    progress["last_run"] = datetime.now(timezone.utc).isoformat()
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def load_existing_cards():
    if CARDS_FILE.exists():
        return pd.read_csv(CARDS_FILE)
    return pd.DataFrame()


def save_cards(new_cards, existing_df, completed_set_titles):
    """Save cards to CSV. Only replaces data for fully completed sets."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if new_cards:
        new_df = pd.DataFrame(new_cards)
        if not existing_df.empty:
            # Only remove old data for sets that were fully re-scanned
            # For incomplete sets, we append (dedup by card id)
            existing_df = existing_df[~existing_df["set"].isin(completed_set_titles)]
            combined = pd.concat([existing_df, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["id"], keep="last")
        else:
            combined = new_df
    else:
        combined = existing_df

    combined.to_csv(CARDS_FILE, index=False)
    return combined


def is_in_cooldown(progress):
    """Check if we're in cooldown after a completed scan."""
    completed_at = progress.get("scan_completed_at")
    if not completed_at:
        return False

    completed_date = datetime.fromisoformat(completed_at)
    cooldown_end = completed_date + timedelta(days=COOLDOWN_DAYS)
    now = datetime.now(timezone.utc)

    if now < cooldown_end:
        days_left = (cooldown_end - now).days
        print(f"Scan completed on {completed_date.strftime('%Y-%m-%d')}.")
        print(f"Cooldown: {days_left} days remaining (resumes {cooldown_end.strftime('%Y-%m-%d')}).")
        return True

    return False


def check_for_new_sets(progress, current_sets):
    """Check if new sets appeared since last scan. Returns new set slugs."""
    known_slugs = set(progress.get("known_sets", []))
    current_slugs = {s[1] for s in current_sets}
    return current_slugs - known_slugs


def build_queue(progress, current_sets):
    """Build scan queue: new sets first, then oldest-scanned sets."""
    known_slugs = set(progress.get("known_sets", []))
    current_slugs = {s[1] for s in current_sets}
    set_lookup = {s[1]: s for s in current_sets}

    new_slugs = current_slugs - known_slugs

    # New sets go first
    queue = []
    for slug in new_slugs:
        title, set_slug, page_count, count = set_lookup[slug]
        queue.append({
            "slug": set_slug,
            "title": title,
            "page_count": page_count,
            "card_count": count,
            "start_page": 1,
            "is_new": True,
        })
        print(f"  New set detected: {title} ({count} cards, {page_count} pages)")

    # Existing sets sorted by staleness (oldest scan first)
    scanned = progress.get("scanned_sets", {})
    existing = []
    for slug in current_slugs - new_slugs:
        if slug not in set_lookup:
            continue
        title, set_slug, page_count, count = set_lookup[slug]
        last_scanned = scanned.get(slug, {}).get("last_scanned", "1970-01-01")
        existing.append((last_scanned, {
            "slug": set_slug,
            "title": title,
            "page_count": page_count,
            "card_count": count,
            "start_page": 1,
            "is_new": False,
        }))

    existing.sort(key=lambda x: x[0])
    queue.extend(item for _, item in existing)

    return queue


def _prepend_new_sets(queue, progress, current_sets):
    """Check for new sets and insert them at the front of the queue."""
    new_slugs = check_for_new_sets(progress, current_sets)
    if new_slugs:
        set_lookup = {s[1]: s for s in current_sets}
        for slug in new_slugs:
            if slug not in set_lookup:
                continue
            title, set_slug, page_count, count = set_lookup[slug]
            queue.insert(0, {
                "slug": set_slug,
                "title": title,
                "page_count": page_count,
                "card_count": count,
                "start_page": 1,
                "is_new": True,
            })
            print(f"  New set detected: {title} ({count} cards, {page_count} pages)")
        progress["known_sets"] = [s[1] for s in current_sets]


def random_sleep():
    delay = random.uniform(MIN_SLEEP, MAX_SLEEP)
    time.sleep(delay)


def scan_set(set_entry, budget_remaining):
    """Scan a single set within the request budget. Returns (cards, pages_done, exhausted_budget)."""
    slug = set_entry["slug"]
    start_page = set_entry["start_page"]
    page_count = set_entry["page_count"]
    cards = []
    pages_done = 0

    for page in range(start_page, page_count + 1):
        if budget_remaining <= 0:
            return cards, pages_done, True

        try:
            url = f"{BASE_URL}/{slug}/{page}"
            response = requests.get(url, timeout=30)

            if response.status_code == 429:
                print(f"  Rate limited at {slug} page {page}. Stopping.")
                return cards, pages_done, True

            if response.status_code != 200:
                print(f"  HTTP {response.status_code} at {slug} page {page}. Skipping page.")
                budget_remaining -= 1
                pages_done += 1
                random_sleep()
                continue

            page_cards = find_tradable_cards(response)
            cards.extend(page_cards)
            budget_remaining -= 1
            pages_done += 1
            random_sleep()

        except requests.exceptions.ConnectionError as e:
            print(f"  Connection error at {slug} page {page}: {e}")
            return cards, pages_done, True
        except requests.exceptions.Timeout:
            print(f"  Timeout at {slug} page {page}. Stopping.")
            return cards, pages_done, True

    return cards, pages_done, False


def run():
    print(f"=== Dragons Lair scan — {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Request budget: {REQUEST_BUDGET}")
    print(f"Sleep range: {MIN_SLEEP}-{MAX_SLEEP}s")
    print(f"Mode: {SCAN_MODE} | Force: {FORCE_RUN}")

    progress = load_progress()

    # Handle full-rescan mode: wipe progress and start fresh
    if SCAN_MODE == "full-rescan":
        print("\n*** Full rescan requested — resetting all progress ***")
        progress = {
            "scanned_sets": {},
            "queue": [],
            "last_run": None,
            "known_sets": [],
            "requests_today": 0,
            "scan_completed_at": None,
        }

    # Check cooldown (skip if manual dispatch)
    if not FORCE_RUN and is_in_cooldown(progress):
        # Still check for new sets — they break cooldown
        print("\nChecking for new sets despite cooldown...")
        current_sets = get_sets(BASE_URL)
        new_slugs = check_for_new_sets(progress, current_sets)
        if not new_slugs:
            print("No new sets found. Skipping run.")
            return
        print(f"Found {len(new_slugs)} new sets — breaking cooldown to scan them.")
        progress["scan_completed_at"] = None

    # Random start delay (0-30 min) to avoid predictable timing
    if os.environ.get("RANDOM_START_DELAY", "1") == "1":
        delay = random.randint(0, 1800)
        print(f"\nRandom start delay: {delay}s ({delay // 60}m {delay % 60}s)")
        time.sleep(delay)

    existing_cards = load_existing_cards()

    # Fetch current set list (1 request)
    print("\nFetching set list...")
    current_sets = get_sets(BASE_URL)
    budget_used = 1
    print(f"Found {len(current_sets)} sets")

    # Check for incomplete set from previous run
    incomplete = progress.get("incomplete_set")

    # Build or resume queue based on mode
    if SCAN_MODE == "new-sets-only":
        # Only scan sets not previously known
        print("\nNew-sets-only mode — scanning only unknown sets")
        new_slugs = check_for_new_sets(progress, current_sets)
        set_lookup = {s[1]: s for s in current_sets}
        queue = []
        for slug in new_slugs:
            title, set_slug, page_count, count = set_lookup[slug]
            queue.append({
                "slug": set_slug,
                "title": title,
                "page_count": page_count,
                "card_count": count,
                "start_page": 1,
                "is_new": True,
            })
            print(f"  New set: {title} ({count} cards, {page_count} pages)")
        progress["known_sets"] = [s[1] for s in current_sets]
        progress["incomplete_set"] = None
    elif not incomplete and not progress.get("queue"):
        print("\nBuilding scan queue...")
        queue = build_queue(progress, current_sets)
        progress["queue"] = queue
        progress["known_sets"] = [s[1] for s in current_sets]
    elif incomplete:
        # Resume incomplete set at the front
        queue = [incomplete] + progress.get("queue", [])
        progress["incomplete_set"] = None
        _prepend_new_sets(queue, progress, current_sets)
    else:
        queue = progress.get("queue", [])
        _prepend_new_sets(queue, progress, current_sets)

    print(f"Queue: {len(queue)} sets remaining")

    if not queue:
        print("Nothing to scan.")
        save_progress(progress)
        return

    # Process queue within budget
    all_new_cards = []
    completed_sets = []

    while queue and budget_used < REQUEST_BUDGET:
        set_entry = queue[0]
        remaining = REQUEST_BUDGET - budget_used
        title = set_entry["title"]
        start = set_entry["start_page"]
        total = set_entry["page_count"]

        print(f"\nScanning: {title} (pages {start}-{total}, ~{total - start + 1} requests)")

        cards, pages_done, hit_limit = scan_set(set_entry, remaining)
        all_new_cards.extend(cards)
        budget_used += pages_done

        if hit_limit and pages_done < (total - start + 1):
            # Didn't finish this set — save resume point
            set_entry["start_page"] = start + pages_done
            progress["incomplete_set"] = set_entry
            queue.pop(0)
            print(f"  Paused at page {set_entry['start_page']}/{total} (budget/rate limit)")
            break
        else:
            # Set complete
            completed_sets.append(set_entry["title"])
            queue.pop(0)
            progress["scanned_sets"][set_entry["slug"]] = {
                "last_scanned": datetime.now(timezone.utc).isoformat(),
                "cards_found": len(cards),
            }
            print(f"  Done: {len(cards)} tradable cards found")

    # Check if full scan is now complete
    if not queue and not progress.get("incomplete_set"):
        progress["scan_completed_at"] = datetime.now(timezone.utc).isoformat()
        print(f"\n*** Full scan complete! Cooldown for {COOLDOWN_DAYS} days. ***")

    # Save results
    progress["queue"] = queue
    progress["requests_today"] = budget_used

    combined = save_cards(all_new_cards, existing_cards, completed_sets)
    save_progress(progress)

    # Summary
    print(f"\n=== Summary ===")
    print(f"Requests used: {budget_used}/{REQUEST_BUDGET}")
    print(f"Sets completed this run: {len(completed_sets)}")
    print(f"New tradable cards found: {len(all_new_cards)}")
    print(f"Total cards in database: {len(combined)}")
    print(f"Sets remaining in queue: {len(queue)}")

    if progress.get("incomplete_set"):
        inc = progress["incomplete_set"]
        print(f"Incomplete set to resume: {inc['title']} (page {inc['start_page']}/{inc['page_count']})")


if __name__ == "__main__":
    run()
