import re

import requests


MOXFIELD_API_URL = "https://api2.moxfield.com/v3/decks/all"
MOXFIELD_DECK_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:www\.)?moxfield\.com/decks/([A-Za-z0-9_-]+)"
)
MOXFIELD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/118.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.moxfield.com/",
}

# Matches lines like: 1 Springleaf Drum (LRW) 261
# or: 4 Lightning Bolt
# or: 1x Sol Ring (CMR) 472
DECKLIST_LINE_PATTERN = re.compile(
    r"^\s*(\d+)x?\s+(.+?)(?:\s+\([A-Za-z0-9]+\)\s*\d*)?\s*$"
)

BOARDS_TO_IMPORT = [
    "commanders",
    "mainboard",
    "sideboard",
    "companions",
    "signatureSpells",
]


class CardImportError(Exception):
    pass


def parse_decklist(text: str) -> list[str]:
    """Parse a standard MTG decklist string into a list of card names.

    Supports the format: <quantity>[x] <card name> [(<set>) <collector#>]
    Example lines:
        1 Springleaf Drum (LRW) 261
        4 Lightning Bolt
        1x Sol Ring
    """
    cards = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue

        match = DECKLIST_LINE_PATTERN.match(line)
        if match:
            card_name = match.group(2).strip()
            if card_name:
                cards.append(card_name)
        else:
            # Treat as bare card name (no quantity prefix)
            if line and not line.startswith("//") and not line.startswith("#"):
                cards.append(line)

    return cards


def extract_moxfield_deck_id(url: str) -> str:
    """Extract the deck public ID from a Moxfield URL."""
    match = MOXFIELD_DECK_URL_PATTERN.search(url)
    if not match:
        raise CardImportError(
            f"Invalid Moxfield URL: {url}\n"
            "Expected format: https://www.moxfield.com/decks/<deck_id>"
        )
    return match.group(1)


def import_from_moxfield(url: str) -> list[str]:
    """Fetch a decklist from a Moxfield deck URL.

    Returns a list of unique card names from the deck's main boards
    (commanders, mainboard, sideboard, companions, signature spells).
    """
    deck_id = extract_moxfield_deck_id(url)
    api_url = f"{MOXFIELD_API_URL}/{deck_id}"

    response = requests.get(api_url, headers=MOXFIELD_HEADERS, timeout=15)

    if response.status_code == 404:
        raise CardImportError(f"Deck not found: {url}")
    if response.status_code != 200:
        raise CardImportError(
            f"Moxfield API returned status {response.status_code}: {response.text[:200]}"
        )

    data = response.json()
    boards = data.get("boards", {})

    cards = []
    seen = set()
    for board_name in BOARDS_TO_IMPORT:
        board = boards.get(board_name, {})
        for entry in board.get("cards", {}).values():
            card_name = entry.get("card", {}).get("name", "")
            if card_name and card_name not in seen:
                cards.append(card_name)
                seen.add(card_name)

    if not cards:
        raise CardImportError(f"No cards found in deck: {url}")

    return cards
