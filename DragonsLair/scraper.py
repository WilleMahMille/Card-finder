import math
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
from tqdm import tqdm

BASE_URL = "https://list.dragonslair.se/product/tag/card-singles/magic/sort:price"


def find_tradable_cards(response: requests.Response):
    soup = BeautifulSoup(response.text, "html.parser")

    rows = soup.find_all("tr", attrs={"data-id": True})
    if not rows:
        return []

    cards = []
    for row in rows:
        data_id = row.get("data-id", "")
        card_name_full = row.get("data-name", "")
        data_price = row.get("data-price", "0")
        data_buyin = row.get("data-buyin", "0")

        price = int(data_price) if data_price and data_price not in ("-", "") else 0
        buyin = int(data_buyin) if data_buyin and data_buyin not in ("-", "") else 0

        if buyin == 0:
            continue

        card_name = card_name_full.split("(")[0].strip()

        card_qualities = {
            "borderless": False,
            "foil": False,
            "extended_art": False,
            "showcase": False,
        }

        name_lower = card_name_full.lower()
        if "foil" in name_lower:
            card_qualities["foil"] = True
        if "borderless" in name_lower:
            card_qualities["borderless"] = True
        if "extended art" in name_lower:
            card_qualities["extended_art"] = True
        if "showcase" in name_lower:
            card_qualities["showcase"] = True

        # TD[1] contains the set name as link text or img alt/title
        tds = row.find_all("td")
        set_name = ""
        if len(tds) > 1:
            set_link = tds[1].find("a")
            if set_link:
                set_name = set_link.get_text().strip()
                if not set_name:
                    img = set_link.find("img")
                    if img:
                        set_name = (img.get("alt") or img.get("title") or "").strip()

        # TD[7] is the Inbyte column
        # "Fullt" = store is full, they don't accept more trade-ins
        # "Max N st" = they accept up to N more
        # Just a price with no restriction = accepting trade-ins
        max_cards = None
        if len(tds) > 7:
            inbyte_text = tds[7].get_text()
            if "Fullt" in inbyte_text:
                max_cards = None  # Store is full, skip this card
                continue
            elif "Max" in inbyte_text:
                max_match = re.search(r"Max\s+(\d+)\s+st", inbyte_text)
                if max_match:
                    max_cards = int(max_match.group(1))
            else:
                max_cards = -1  # No stated limit

        # Extract stock info
        stock_span = row.find("span", class_="stock")
        in_stock = int(stock_span.get_text()) if stock_span else 0

        cards.append({
            "id": data_id,
            "name": card_name,
            "full_name": card_name_full,
            "set": set_name,
            "price": price,
            "trade_in_price": buyin,
            "max_cards": max_cards,
            "in_stock": in_stock,
            "qualities": card_qualities,
        })

    return cards


def get_sets(url: str):
    response = requests.get(url, timeout=30)
    soup = BeautifulSoup(response.text, "html.parser")

    # Find the "Set" filter container specifically
    set_container = None
    for container in soup.find_all("div", class_="filter-container"):
        h3 = container.find("h3")
        if h3 and h3.get_text().strip().startswith("Set"):
            set_container = container
            break

    if not set_container:
        print("Warning: Could not find 'Set' filter container")
        return []

    sets = []
    for link in set_container.find_all("a", class_="facet"):
        href = link.get("href", "")
        set_slug = href.split("/")[-1]
        title = link.get("title", "").strip()

        count_span = link.find_previous_sibling("span", class_="count")
        if not count_span:
            parent = link.parent
            if parent:
                count_span = parent.find("span", class_="count")

        count = 0
        if count_span:
            count_text = count_span.get_text().strip().replace("(", "").replace(")", "")
            count = int(count_text) if count_text.isdigit() else 0

        page_count = math.ceil(count / 36) if count > 0 else 1

        sets.append((title, set_slug, page_count, count))

    return sets


def search_sets_for_tradable_cards(url: str, num_cards: int = -1):
    sets = get_sets(url)
    cards = []

    for title, set_slug, page_count, count in tqdm(sets, desc="Searching sets"):
        if 0 < num_cards <= len(cards):
            break

        try:
            for page in tqdm(range(1, page_count + 1), desc=f"{title}", leave=False):
                response = requests.get(f"{url}/{set_slug}/{page}", timeout=30)
                cards.extend(find_tradable_cards(response))
                time.sleep(0.5)
        except requests.exceptions.ConnectionError as e:
            print(f"Warning: Could not connect to {url}/{set_slug}")
            print(e)
            continue

    if num_cards > 0:
        cards = cards[:num_cards]

    return cards


def parse_to_dataframe(cards: list[dict]):
    return pd.DataFrame(cards)
