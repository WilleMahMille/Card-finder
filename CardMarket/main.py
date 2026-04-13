import hashlib
import json
import os
import sys
import glob
import traceback
from datetime import datetime
from functools import wraps

import tqdm
from card_editor import edit_card_list
from card_import import CardImportError, import_from_moxfield, parse_decklist
from market_api import CardApi, ShippingApi
from collections import defaultdict
import pandas as pd
import argparse
import numpy as np


# =============================================================================
# Configuration Constants
# =============================================================================

RESOURCES_DIR = os.path.join(os.path.dirname(__file__), "Resources")
DESIRED_CARDS_DIR = os.path.join(RESOURCES_DIR, "DesiredCards")
LISTINGS_DIR = os.path.join(RESOURCES_DIR, "Listings")

TO_COUNTRY = "sweden"
LANGUAGE = "English"
MAX_PRODUCT_VERSIONS_TO_CHECK = 1


# =============================================================================
# Error Handling Utilities
# =============================================================================

class CardMarketError(Exception):
    """Custom exception for CardMarket tool errors."""
    pass


class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_error(message: str):
    """Print error message in red."""
    print(f"{Colors.RED}[ERROR] {message}{Colors.RESET}")


def print_warning(message: str):
    """Print warning message in yellow."""
    print(f"{Colors.YELLOW}[WARNING] {message}{Colors.RESET}")


def print_success(message: str):
    """Print success message in green."""
    print(f"{Colors.GREEN}[SUCCESS] {message}{Colors.RESET}")


def print_info(message: str):
    """Print info message in cyan."""
    print(f"{Colors.CYAN}[INFO] {message}{Colors.RESET}")


def safe_execute(func):
    """Decorator to wrap functions with error handling."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CardMarketError as e:
            print_error(str(e))
            return None
        except FileNotFoundError as e:
            print_error(f"File not found: {e.filename}")
            return None
        except pd.errors.EmptyDataError:
            print_error("The file is empty or has no valid data.")
            return None
        except json.JSONDecodeError as e:
            print_error(f"Invalid JSON format: {e.msg}")
            return None
        except Exception as e:
            print_error(f"Unexpected error: {str(e)}")
            print_error(f"Traceback:\n{traceback.format_exc()}")
            return None
    return wrapper


# =============================================================================
# File Management Functions
# =============================================================================

def get_available_card_lists() -> list[tuple[str, str]]:
    """
    Scan DesiredCards directory for available CSV files.
    Returns list of tuples: (display_name, full_path)
    """
    if not os.path.exists(DESIRED_CARDS_DIR):
        print_warning(f"DesiredCards directory not found: {DESIRED_CARDS_DIR}")
        return []

    csv_files = glob.glob(os.path.join(DESIRED_CARDS_DIR, "*.csv"))
    result = []
    for filepath in sorted(csv_files):
        filename = os.path.basename(filepath)
        display_name = os.path.splitext(filename)[0]
        result.append((display_name, filepath))
    return result


def get_available_listings() -> list[tuple[str, str]]:
    """
    Scan Listings directory for available CSV files.
    Returns list of tuples: (display_name, full_path)
    """
    if not os.path.exists(LISTINGS_DIR):
        print_warning(f"Listings directory not found: {LISTINGS_DIR}")
        return []

    csv_files = glob.glob(os.path.join(LISTINGS_DIR, "*.csv"))
    result = []
    for filepath in sorted(csv_files, reverse=True):  # Most recent first
        filename = os.path.basename(filepath)
        display_name = os.path.splitext(filename)[0]
        result.append((display_name, filepath))
    return result


@safe_execute
def load_desired_cards(path: str) -> list[str]:
    """
    Load desired cards from a CSV file.
    Expects a CSV with a 'card_name' column or single column of card names.
    """
    if not os.path.exists(path):
        raise CardMarketError(f"Card list file not found: {path}")

    df = pd.read_csv(path)

    if 'card_name' in df.columns:
        cards = df['card_name'].dropna().tolist()
    elif len(df.columns) == 1:
        cards = df.iloc[:, 0].dropna().tolist()
    else:
        raise CardMarketError(
            f"Invalid card list format. Expected 'card_name' column or single column. "
            f"Found columns: {list(df.columns)}"
        )

    cards = [str(card).strip() for card in cards if str(card).strip()]
    print_success(f"Loaded {len(cards)} cards from {os.path.basename(path)}")
    return cards


@safe_execute
def load_listings(path: str) -> pd.DataFrame:
    """Load listings from a CSV file."""
    if not os.path.exists(path):
        raise CardMarketError(f"Listings file not found: {path}")

    df = pd.read_csv(path)
    required_columns = {'seller', 'card_name', 'price', 'country', 'link'}

    if not required_columns.issubset(set(df.columns)):
        missing = required_columns - set(df.columns)
        raise CardMarketError(f"Listings file missing required columns: {missing}")

    print_success(f"Loaded {len(df)} listings from {os.path.basename(path)}")
    return df


def save_listings(df: pd.DataFrame, name: str = None) -> str:
    """
    Save listings to a CSV file in the Listings directory.
    Uses format: listings_df_YYYYMMDD.out.csv or listings_df_<name>.out.csv
    Returns the path to the saved file.
    """
    if not os.path.exists(LISTINGS_DIR):
        os.makedirs(LISTINGS_DIR)

    if name:
        filename = f"listings_df_{name}.out.csv"
    else:
        date_str = datetime.now().strftime("%Y%m%d")
        filename = f"listings_df_{date_str}.out.csv"

    filepath = os.path.join(LISTINGS_DIR, filename)

    try:
        df.to_csv(filepath, index=False)
        print_success(f"Saved {len(df)} listings to {filename}")
        return filepath
    except Exception as e:
        print_error(f"Failed to save listings: {str(e)}")
        return None


# =============================================================================
# Core Algorithm Functions
# =============================================================================

def calculate_shipping_price(
    filtered_df: pd.DataFrame,
    shipping_dict: dict,
    previous_node_path: list,
    current_node_index: int,
    current_value: float,
    value_increase: float
) -> float:
    """
    Calculate the shipping price or increase in shipping price for a given seller/node.

    Since shipping price increases with card value at certain rates, we handle:
    - Current seller already in path, value doesn't reach new threshold
    - Current seller already in path, value reaches new threshold
    - Current seller not in path (shipping = new threshold based on value_increase)
    """
    try:
        country = filtered_df.iloc[current_node_index]['country']
        country_key = country.upper().replace(" ", "_")

        if country_key not in shipping_dict:
            print_warning(f"No shipping data for country: {country}")
            return 0.0

        shipping_price_list = shipping_dict[country_key]

        previous_shipping_price = shipping_price_list[0]['price']
        new_shipping_price = previous_shipping_price

        for shipping_price in shipping_price_list:
            if current_value > shipping_price['maxValue']:
                previous_shipping_price = shipping_price['price']
                new_shipping_price = shipping_price['price']
            elif current_value + value_increase > shipping_price['maxValue']:
                new_shipping_price = shipping_price['price']
            else:
                break

        shipping_price_increase = new_shipping_price - previous_shipping_price

        if current_node_index in previous_node_path:
            return shipping_price_increase
        else:
            return new_shipping_price

    except Exception as e:
        print_error(f"Error calculating shipping price: {str(e)}")
        return 0.0


def find_cheapest_seller_group(
    filtered_df: pd.DataFrame,
    shipping_dict: dict,
    desired_cards_set: set
) -> tuple[dict, float]:
    """
    Find the optimal combination of sellers to minimize total cost.

    Uses dynamic programming to find the minimum cost path through sellers
    that covers all desired cards.

    Returns:
        tuple: (optimal_seller_groups dict, minimum_cost float)
    """
    try:
        sorted_desired_cards_set = sorted(list(desired_cards_set))

        # Create adjacency matrix: sellers x cards
        adjacency_matrix = np.zeros((len(filtered_df), len(sorted_desired_cards_set)))
        for i, row in filtered_df.iterrows():
            for j, card in enumerate(sorted_desired_cards_set):
                if pd.notna(row[card]):
                    adjacency_matrix[i][j] = row[card]
                else:
                    adjacency_matrix[i][j] = float('inf')

        # Path matrix: (cost, path) for each seller-card combination
        path_matrix = [[(float('inf'), []) for _ in range(len(sorted_desired_cards_set))]
                       for _ in range(len(filtered_df))]

        # Initialize first column
        for i in range(len(filtered_df)):
            shipping_price = calculate_shipping_price(
                filtered_df=filtered_df,
                shipping_dict=shipping_dict,
                previous_node_path=[],
                current_node_index=i,
                current_value=0,
                value_increase=adjacency_matrix[i][0]
            )
            path_matrix[i][0] = (adjacency_matrix[i][0] + shipping_price, [i])

        # Dynamic programming: iterate through cards
        for j in tqdm.tqdm(range(1, len(sorted_desired_cards_set)), desc="Optimizing"):
            for i in range(len(filtered_df)):
                (previous_node_price, previous_node_path) = path_matrix[i][j-1]
                for k in range(len(filtered_df)):
                    (node_price, node_path) = path_matrix[k][j]
                    if adjacency_matrix[k][j] == float('inf'):
                        continue

                    price = previous_node_price
                    price += calculate_shipping_price(
                        filtered_df=filtered_df,
                        shipping_dict=shipping_dict,
                        previous_node_path=previous_node_path,
                        current_node_index=k,
                        current_value=price,
                        value_increase=adjacency_matrix[k][j]
                    )
                    price += adjacency_matrix[k][j]

                    if price < node_price:
                        path_matrix[k][j] = (price, previous_node_path + [k])

        # Find minimum cost path
        min_cost = float('inf')
        min_path = []
        for i in range(len(filtered_df)):
            if path_matrix[i][-1][0] < min_cost:
                min_cost = path_matrix[i][-1][0]
                min_path = path_matrix[i][-1][1]

        print_info(f"Minimum cost: {min_cost:.2f}")
        print_info(f"Sellers in optimal path: {[filtered_df.iloc[i]['seller'] for i in set(min_path)]}")

        # Build result dictionary
        optimal_seller_groups = defaultdict(list)
        for i in range(len(min_path)):
            optimal_seller_groups[filtered_df.iloc[min_path[i]]['seller']].append(
                sorted_desired_cards_set[i]
            )

        return optimal_seller_groups, min_cost

    except Exception as e:
        print_error(f"Error in find_cheapest_seller_group: {str(e)}")
        print_error(traceback.format_exc())
        return {}, float('inf')


def filter_sellers_df(sellers_df: pd.DataFrame, card_names: list) -> pd.DataFrame:
    """
    Filter out redundant sellers, keeping only the cheapest per card combination.

    For each unique combination of cards a seller offers, keeps only the cheapest
    seller per country.
    """
    try:
        output_df = pd.DataFrame(columns=sellers_df.columns)

        # Extract all unique card combinations
        combinations = []
        for _, row in sellers_df.iterrows():
            cards_sold = [card for card in card_names if pd.notna(row[card])]
            cards_sold.sort()
            if cards_sold not in combinations:
                combinations.append(cards_sold)

        # Filter sellers for each combination
        for combination in combinations:
            if not combination:
                continue

            other_cards = [card for card in card_names if card not in combination]
            cond_has_price = sellers_df[combination].notna().all(axis=1)
            cond_null_others = sellers_df[other_cards].isna().all(axis=1)
            mask = cond_has_price & cond_null_others
            sellers_subset = sellers_df[mask].copy()

            if sellers_subset.empty:
                continue

            # Sort by total price for this combination
            sellers_subset = sellers_subset.sort_values(by=combination, ascending=True)

            # Keep cheapest per country
            temp_out_df = pd.DataFrame(columns=sellers_df.columns)
            for _, row in sellers_subset.iterrows():
                country_mask = temp_out_df['country'] == row['country']
                if country_mask.any():
                    existing_row = temp_out_df[country_mask].iloc[0]
                    existing_total = sum(existing_row[card] for card in combination
                                        if pd.notna(existing_row[card]))
                    current_total = sum(row[card] for card in combination
                                       if pd.notna(row[card]))

                    if current_total < existing_total:
                        temp_out_df = temp_out_df[~country_mask]
                        new_row_df = pd.DataFrame([row])
                        if temp_out_df.empty:
                            temp_out_df = new_row_df
                        else:
                            temp_out_df = pd.concat([temp_out_df, new_row_df], ignore_index=True)
                else:
                    new_row_df = pd.DataFrame([row])
                    if temp_out_df.empty:
                        temp_out_df = new_row_df
                    else:
                        temp_out_df = pd.concat([temp_out_df, new_row_df], ignore_index=True)

            if not temp_out_df.empty:
                if output_df.empty:
                    output_df = temp_out_df
                else:
                    output_df = pd.concat([output_df, temp_out_df], ignore_index=True)

        print_info(f"Filtered to {len(output_df)} unique sellers.")
        return output_df

    except Exception as e:
        print_error(f"Error filtering sellers: {str(e)}")
        return sellers_df


def create_sellers_dataframe(
    listings: pd.DataFrame,
    card_names: list[str]
) -> tuple[pd.DataFrame, list[str]]:
    """
    Transform listings into a seller-focused DataFrame.

    Creates DataFrame where each row is a seller, and columns are card prices.
    """
    try:
        found_cards = {}
        for _, listing in listings.iterrows():
            card_name = str(listing['card_name']).lower()
            if card_name in card_names:
                found_cards[card_name] = True

        found_cards = list(found_cards.keys())
        print_info(f"Found {len(found_cards)} of {len(card_names)} desired cards in listings.")

        sellers_df = pd.DataFrame(columns=["seller", "country", "link", *found_cards])

        for _, listing in listings.iterrows():
            seller = listing['seller']
            card_price = listing['price']
            card_name = str(listing['card_name']).lower()

            if card_name not in card_names:
                continue

            if seller in sellers_df['seller'].values:
                sellers_df.loc[sellers_df['seller'] == seller, card_name] = card_price
            else:
                row = {
                    "seller": seller,
                    "country": listing['country'],
                    **{card.lower(): None for card in found_cards}
                }
                row[card_name] = card_price
                new_row_df = pd.DataFrame([row])
                if sellers_df.empty:
                    sellers_df = new_row_df
                else:
                    sellers_df = pd.concat([sellers_df, new_row_df], ignore_index=True)

        return sellers_df, found_cards

    except Exception as e:
        print_error(f"Error creating sellers dataframe: {str(e)}")
        return pd.DataFrame(), []


def parse_raw_data(
    raw_data: list[dict],
    previous_listings: pd.DataFrame = None
) -> pd.DataFrame:
    """
    Parse raw scraper data into a DataFrame with deduplication.

    Uses MD5 hash of listing (excluding link) to detect duplicates.
    """
    try:
        if previous_listings is not None and not previous_listings.empty:
            listings = previous_listings.copy()
        else:
            listings = pd.DataFrame(columns=["seller", "card_name", "price", "country", "link", "hash"])

        new_count = 0
        for listing in raw_data:
            listing_for_hash = {k: v for k, v in listing.items() if k != 'link'}
            listing_str = json.dumps(listing_for_hash, sort_keys=True)
            hash_value = hashlib.md5(listing_str.encode('utf-8')).hexdigest()

            if hash_value in listings['hash'].values:
                continue

            row = {
                "seller": listing['seller'],
                "card_name": listing['card_name'],
                "price": listing['price'],
                "country": listing['country'],
                "link": listing['link'],
                "hash": hash_value
            }

            new_row_df = pd.DataFrame([row])
            if listings.empty:
                listings = new_row_df
            else:
                listings = pd.concat([listings, new_row_df], ignore_index=True)
            new_count += 1

        print_info(f"Added {new_count} new listings. Total: {len(listings)}")
        return listings

    except Exception as e:
        print_error(f"Error parsing raw data: {str(e)}")
        return previous_listings if previous_listings is not None else pd.DataFrame()


# =============================================================================
# Menu System
# =============================================================================

class AppState:
    """Application state container."""
    def __init__(self):
        self.desired_cards: list[str] = []
        self.listings_df: pd.DataFrame = pd.DataFrame()
        self.shipping_dict: dict = None
        self.to_country: str = TO_COUNTRY


def clear_screen():
    """Clear the terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def display_main_menu(state: AppState):
    """Display the main menu with current state information."""
    clear_screen()
    print(f"{Colors.BOLD}{Colors.CYAN}")
    print("=" * 50)
    print("       CardMarket Price Optimizer")
    print("=" * 50)
    print(f"{Colors.RESET}")

    # Display current state
    print(f"{Colors.BOLD}Current State:{Colors.RESET}")
    if state.desired_cards:
        print(f"  - Desired cards: {Colors.GREEN}Loaded{Colors.RESET} ({len(state.desired_cards)} cards)")
    else:
        print(f"  - Desired cards: {Colors.YELLOW}Not loaded{Colors.RESET}")

    if not state.listings_df.empty:
        print(f"  - Listings: {Colors.GREEN}Loaded{Colors.RESET} ({len(state.listings_df)} entries)")
    else:
        print(f"  - Listings: {Colors.YELLOW}Not loaded{Colors.RESET}")

    print(f"  - Target country: {Colors.CYAN}{state.to_country}{Colors.RESET}")
    print()

    # Menu options
    print(f"{Colors.BOLD}Options:{Colors.RESET}")
    print("  1. Manage desired cards")
    print("  2. Load/Manage listings")
    print("  3. Gather new listings")
    print("  4. Find cheapest sellers")
    print("  5. Settings")
    print("  0. Exit")
    print()


def menu_load_cards(state: AppState):
    """Menu for managing desired cards."""
    while True:
        clear_screen()
        print(f"{Colors.BOLD}Manage Desired Cards{Colors.RESET}")
        print("-" * 30)

        if state.desired_cards:
            print(f"\nCurrently loaded: {Colors.GREEN}{len(state.desired_cards)} cards{Colors.RESET}")
        else:
            print(f"\nCurrently loaded: {Colors.YELLOW}None{Colors.RESET}")

        available = get_available_card_lists()

        print(f"\n{Colors.BOLD}Load:{Colors.RESET}")
        for i, (name, path) in enumerate(available, 1):
            try:
                df = pd.read_csv(path)
                count = len(df)
            except:
                count = "?"
            print(f"  {i}. {name} ({count} cards)")

        base = len(available)
        print(f"  {base + 1}. Load from custom path")
        print(f"  {base + 2}. Import from decklist (e.g. 1 Sol Ring (CMR) 472)")
        print(f"  {base + 3}. Import from Moxfield URL")

        print(f"\n{Colors.BOLD}Edit:{Colors.RESET}")
        print(f"  {base + 4}. Edit cards")
        print(f"  {base + 5}. Save list to file")

        print("\n  0. Back to main menu")
        print()

        try:
            choice = input("Select option: ").strip()

            if choice == "0":
                return

            choice_num = int(choice)

            if 1 <= choice_num <= base:
                _, path = available[choice_num - 1]
                cards = load_desired_cards(path)
                if cards:
                    state.desired_cards = cards
            elif choice_num == base + 1:
                custom_path = input("Enter path to CSV file: ").strip()
                cards = load_desired_cards(custom_path)
                if cards:
                    state.desired_cards = cards
            elif choice_num == base + 2:
                _menu_import_decklist(state)
            elif choice_num == base + 3:
                _menu_import_moxfield(state)
            elif choice_num == base + 4:
                _menu_edit_cards(state)
            elif choice_num == base + 5:
                _menu_save_card_list(state)
            else:
                print_warning("Invalid option")
                input("\nPress Enter to continue...")

        except ValueError:
            print_warning("Please enter a number")
            input("\nPress Enter to continue...")


def _menu_edit_cards(state: AppState):
    """Open the interactive card editor."""
    result = edit_card_list(state.desired_cards)
    if result is not None:
        state.desired_cards = result
        print_success(f"Saved {len(result)} cards")
    else:
        print_info("Edit cancelled")
    input("\nPress Enter to continue...")


def _menu_save_card_list(state: AppState):
    """Save the current card list to a CSV file."""
    if not state.desired_cards:
        print_warning("No cards to save")
        input("\nPress Enter to continue...")
        return

    name = input("File name (without .csv): ").strip()
    if not name:
        print_warning("No name provided")
        input("\nPress Enter to continue...")
        return

    filepath = os.path.join(DESIRED_CARDS_DIR, f"{name}.csv")
    if os.path.exists(filepath):
        if input(f"'{name}.csv' already exists. Overwrite? (y/n): ").strip().lower() != 'y':
            input("\nPress Enter to continue...")
            return

    df = pd.DataFrame({"card_name": state.desired_cards})
    df.to_csv(filepath, index=False)
    print_success(f"Saved {len(state.desired_cards)} cards to {name}.csv")
    input("\nPress Enter to continue...")


def _menu_import_decklist(state: AppState):
    """Import cards from a pasted decklist."""
    print("\nPaste your decklist below (empty line to finish):")
    lines = []
    while True:
        line = input()
        if not line.strip():
            break
        lines.append(line)

    if not lines:
        print_warning("No input provided")
        input("\nPress Enter to continue...")
        return

    text = "\n".join(lines)
    cards = parse_decklist(text)

    if cards:
        state.desired_cards = cards
        print_success(f"Imported {len(cards)} cards from decklist")
    else:
        print_warning("Could not parse any cards from the input")
    input("\nPress Enter to continue...")


def _menu_import_moxfield(state: AppState):
    """Import cards from a Moxfield deck URL."""
    url = input("Enter Moxfield deck URL: ").strip()
    if not url:
        print_warning("No URL provided")
        input("\nPress Enter to continue...")
        return

    try:
        print_info("Fetching deck from Moxfield...")
        cards = import_from_moxfield(url)
        state.desired_cards = cards
        print_success(f"Imported {len(cards)} cards from Moxfield")
    except CardImportError as e:
        print_error(str(e))
    except Exception as e:
        print_error(f"Failed to import from Moxfield: {str(e)}")
    input("\nPress Enter to continue...")


def menu_manage_listings(state: AppState):
    """Menu for managing listings."""
    clear_screen()
    print(f"{Colors.BOLD}Load/Manage Listings{Colors.RESET}")
    print("-" * 30)

    available = get_available_listings()

    print("\nOptions:")
    if available:
        print("\nAvailable listings files:")
        for i, (name, path) in enumerate(available, 1):
            try:
                df = pd.read_csv(path)
                count = len(df)
            except:
                count = "?"
            print(f"  {i}. {name} ({count} listings)")

    base_option = len(available) + 1
    print(f"\n  {base_option}. Enter custom path")
    print(f"  {base_option + 1}. Export current listings")
    print(f"  {base_option + 2}. Clear current listings")
    print("  0. Back to main menu")
    print()

    try:
        choice = input("Select option: ").strip()

        if choice == "0":
            return

        choice_num = int(choice)

        if 1 <= choice_num <= len(available):
            _, path = available[choice_num - 1]
            df = load_listings(path)
            if df is not None:
                state.listings_df = df
        elif choice_num == base_option:
            custom_path = input("Enter path to CSV file: ").strip()
            df = load_listings(custom_path)
            if df is not None:
                state.listings_df = df
        elif choice_num == base_option + 1:
            if state.listings_df.empty:
                print_warning("No listings to export")
            else:
                name = input("Export name (leave blank for date): ").strip() or None
                save_listings(state.listings_df, name)
        elif choice_num == base_option + 2:
            if input("Are you sure? (y/n): ").strip().lower() == 'y':
                state.listings_df = pd.DataFrame()
                print_success("Listings cleared")
        else:
            print_warning("Invalid option")

    except ValueError:
        print_warning("Please enter a number")

    input("\nPress Enter to continue...")


def menu_gather_listings(state: AppState):
    """Menu for gathering new listings via web scraping."""
    clear_screen()
    print(f"{Colors.BOLD}Gather New Listings{Colors.RESET}")
    print("-" * 30)

    if not state.desired_cards:
        print_warning("Please load desired cards first!")
        input("\nPress Enter to continue...")
        return

    print(f"\nWill gather listings for {len(state.desired_cards)} cards.")
    if not state.listings_df.empty:
        print(f"Current listings: {len(state.listings_df)} (new listings will be added)")

    # Determine which cards still need scraping
    if not state.listings_df.empty:
        existing_cards = set(state.listings_df['card_name'].str.lower().unique())
        cards_to_gather = [c for c in state.desired_cards
                          if c.lower() not in existing_cards]
        print(f"Cards needing data: {len(cards_to_gather)}")
    else:
        cards_to_gather = state.desired_cards

    print("\nOptions:")
    print("  1. Active mode (automatic scraping)")
    print("  2. Passive mode (manual browsing)")
    print("  3. Active mode headless (no browser window)")
    print("  0. Cancel")
    print()

    choice = input("Select mode: ").strip()

    if choice == "0":
        return

    headless = choice == "3"

    try:
        print_info("Initializing CardApi...")
        api = CardApi(headless=headless)

        if choice in ("1", "3"):
            print_info("Starting active scraping mode...")
            raw_data = api.gather_data(cards_to_gather)
        elif choice == "2":
            print_info("Starting passive mode. Browse CardMarket manually.")
            print_info("The scraper will collect listings from pages you visit.")
            raw_data = api.gather_data(cards_to_gather)
        else:
            print_warning("Invalid option")
            api.close()
            return

        api.close()

        # Parse and merge new data
        state.listings_df = parse_raw_data(raw_data, state.listings_df)

        # Offer to save
        if input("\nSave listings now? (y/n): ").strip().lower() == 'y':
            name = input("Export name (leave blank for date): ").strip() or None
            save_listings(state.listings_df, name)

    except Exception as e:
        print_error(f"Error during scraping: {str(e)}")
        print_error(traceback.format_exc())

    input("\nPress Enter to continue...")


def menu_find_cheapest(state: AppState):
    """Menu for finding cheapest seller combinations."""
    clear_screen()
    print(f"{Colors.BOLD}Find Cheapest Sellers{Colors.RESET}")
    print("-" * 30)

    if not state.desired_cards:
        print_warning("Please load desired cards first!")
        input("\nPress Enter to continue...")
        return

    if state.listings_df.empty:
        print_warning("Please load or gather listings first!")
        input("\nPress Enter to continue...")
        return

    card_names = [card.lower() for card in state.desired_cards]

    print_info(f"Processing {len(state.listings_df)} listings for {len(card_names)} cards...")

    try:
        # Create sellers dataframe
        sellers_df, found_cards = create_sellers_dataframe(state.listings_df, card_names)

        if sellers_df.empty:
            print_error("No matching sellers found!")
            input("\nPress Enter to continue...")
            return

        print_info(f"Found {len(sellers_df)} sellers with {len(found_cards)} cards.")

        # Filter redundant sellers
        filtered_df = filter_sellers_df(sellers_df, found_cards)

        # Load or fetch shipping dictionary
        if state.shipping_dict is None:
            print_info(f"Fetching shipping prices for {state.to_country}...")
            try:
                state.shipping_dict = ShippingApi.get_shipping_prices(state.to_country)
            except Exception as e:
                print_error(f"Failed to fetch shipping prices: {str(e)}")
                # Try to load from file
                shipping_path = os.path.join(os.path.dirname(__file__), "shipping_dict.json")
                if os.path.exists(shipping_path):
                    print_info("Loading shipping data from cached file...")
                    with open(shipping_path, 'r') as f:
                        state.shipping_dict = json.load(f)
                else:
                    print_error("No shipping data available. Cannot proceed.")
                    input("\nPress Enter to continue...")
                    return

        # Find optimal seller groups
        print_info("Finding optimal seller combination...")
        desired_cards_set = set(found_cards)
        optimal_groups, min_cost = find_cheapest_seller_group(
            filtered_df, state.shipping_dict, desired_cards_set
        )

        if not optimal_groups:
            print_error("Could not find a valid seller combination!")
            input("\nPress Enter to continue...")
            return

        # Display results
        print(f"\n{Colors.BOLD}{Colors.GREEN}=== Results ==={Colors.RESET}")
        total_card_cost = 0

        for seller, cards in optimal_groups.items():
            print(f"\n{Colors.BOLD}Seller: {seller}{Colors.RESET}")
            for card in cards:
                price = filtered_df.loc[filtered_df['seller'] == seller, card].values[0]
                link_values = state.listings_df.loc[
                    (state.listings_df['seller'] == seller) &
                    (state.listings_df['card_name'].str.lower() == card.lower()),
                    'link'
                ].values
                link = link_values[0] if len(link_values) > 0 else None
                print(f"  - {card}: {price:.2f}€" + (f" ({link})" if link else ""))
                total_card_cost += price

        print(f"\n{Colors.BOLD}Total card cost: {total_card_cost:.2f}€{Colors.RESET}")
        print(f"{Colors.BOLD}Total with shipping: {min_cost:.2f}€{Colors.RESET}")

        # Offer to save results
        if input("\nSave results to file? (y/n): ").strip().lower() == 'y':
            output_path = input("Output file path (default: output.txt): ").strip() or "output.txt"
            try:
                with open(output_path, 'w') as f:
                    f.write("CardMarket Price Optimizer Results\n")
                    f.write("=" * 40 + "\n\n")
                    for seller, cards in optimal_groups.items():
                        f.write(f"Seller: {seller}\n")
                        for card in cards:
                            price = filtered_df.loc[filtered_df['seller'] == seller, card].values[0]
                            f.write(f"  - {card}: {price:.2f}€\n")
                        f.write("\n")
                    f.write(f"Total card cost: {total_card_cost:.2f}€\n")
                    f.write(f"Total with shipping: {min_cost:.2f}€\n")
                print_success(f"Results saved to {output_path}")
            except Exception as e:
                print_error(f"Failed to save results: {str(e)}")

    except Exception as e:
        print_error(f"Error finding cheapest sellers: {str(e)}")
        print_error(traceback.format_exc())

    input("\nPress Enter to continue...")


def menu_settings(state: AppState):
    """Menu for application settings."""
    clear_screen()
    print(f"{Colors.BOLD}Settings{Colors.RESET}")
    print("-" * 30)

    print(f"\nCurrent settings:")
    print(f"  1. Target country: {state.to_country}")
    print(f"  2. Clear shipping cache")
    print("  0. Back to main menu")
    print()

    choice = input("Select option: ").strip()

    if choice == "1":
        new_country = input(f"Enter target country (current: {state.to_country}): ").strip()
        if new_country:
            state.to_country = new_country.lower()
            state.shipping_dict = None  # Clear cached shipping data
            print_success(f"Target country set to: {state.to_country}")
    elif choice == "2":
        state.shipping_dict = None
        print_success("Shipping cache cleared")

    input("\nPress Enter to continue...")


def run_interactive_menu():
    """Run the interactive menu loop."""
    state = AppState()

    while True:
        display_main_menu(state)
        choice = input("Select option: ").strip()

        if choice == "0":
            print("\nGoodbye!")
            break
        elif choice == "1":
            menu_load_cards(state)
        elif choice == "2":
            menu_manage_listings(state)
        elif choice == "3":
            menu_gather_listings(state)
        elif choice == "4":
            menu_find_cheapest(state)
        elif choice == "5":
            menu_settings(state)
        else:
            print_warning("Invalid option")
            input("\nPress Enter to continue...")


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="CardMarket Price Optimizer - Find the cheapest seller combinations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                    # Interactive menu
  python main.py --cards Resources/DesiredCards/default.csv --gather
  python main.py --decklist my_deck.txt --gather    # Import from decklist file
  python main.py --moxfield https://www.moxfield.com/decks/abc123 --gather
  python main.py --listings Resources/Listings/listings_df_20260121.out.csv --find-cheapest
        """
    )
    parser.add_argument(
        "--cards",
        type=str,
        help="Path to CSV file containing desired card names"
    )
    parser.add_argument(
        "--decklist",
        type=str,
        help="Path to a decklist file (standard MTG format: '1 Card Name (SET) 123')"
    )
    parser.add_argument(
        "--moxfield",
        type=str,
        help="Moxfield deck URL to import cards from"
    )
    parser.add_argument(
        "--listings",
        type=str,
        help="Path to CSV file containing listings data"
    )
    parser.add_argument(
        "--gather",
        action="store_true",
        help="Gather new listings via web scraping (adds to existing)"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run the browser in headless mode (no window)"
    )
    parser.add_argument(
        "--find-cheapest",
        action="store_true",
        help="Find the cheapest seller combination"
    )
    parser.add_argument(
        "--shipping-dict",
        type=str,
        help="Path to shipping dictionary JSON file"
    )
    parser.add_argument(
        "--export",
        type=str,
        help="Custom name for exported listings file"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="File to write analysis results to"
    )
    parser.add_argument(
        "--country",
        type=str,
        default=TO_COUNTRY,
        help=f"Target country for shipping (default: {TO_COUNTRY})"
    )

    args = parser.parse_args()

    # If no action arguments provided, run interactive menu
    has_action = args.gather or args.find_cheapest
    has_input = args.cards or args.decklist or args.moxfield or args.listings
    if not has_action and not has_input:
        run_interactive_menu()
        return

    # CLI mode
    state = AppState()
    state.to_country = args.country

    # Load cards from one of the available sources
    if args.cards:
        cards = load_desired_cards(args.cards)
        if cards:
            state.desired_cards = cards
        else:
            print_error("Failed to load cards. Exiting.")
            sys.exit(1)
    elif args.decklist:
        try:
            with open(args.decklist, 'r') as f:
                text = f.read()
            cards = parse_decklist(text)
            if cards:
                state.desired_cards = cards
                print_success(f"Imported {len(cards)} cards from decklist")
            else:
                print_error("No cards found in decklist file.")
                sys.exit(1)
        except FileNotFoundError:
            print_error(f"Decklist file not found: {args.decklist}")
            sys.exit(1)
    elif args.moxfield:
        try:
            cards = import_from_moxfield(args.moxfield)
            state.desired_cards = cards
            print_success(f"Imported {len(cards)} cards from Moxfield")
        except CardImportError as e:
            print_error(str(e))
            sys.exit(1)

    # Load listings if provided
    if args.listings:
        df = load_listings(args.listings)
        if df is not None:
            state.listings_df = df

    # Load shipping dictionary if provided
    if args.shipping_dict:
        try:
            with open(args.shipping_dict, 'r') as f:
                state.shipping_dict = json.load(f)
            print_success(f"Loaded shipping data from {args.shipping_dict}")
        except Exception as e:
            print_warning(f"Failed to load shipping dictionary: {str(e)}")

    # Gather new listings
    if args.gather:
        if not state.desired_cards:
            print_error("Cannot gather listings without card list. Use --cards option.")
            sys.exit(1)

        try:
            # Determine cards to gather
            if not state.listings_df.empty:
                existing_cards = set(state.listings_df['card_name'].str.lower().unique())
                cards_to_gather = [c for c in state.desired_cards
                                  if c.lower() not in existing_cards]
            else:
                cards_to_gather = state.desired_cards

            print_info(f"Gathering listings for {len(cards_to_gather)} cards...")
            api = CardApi(headless=args.headless)
            raw_data = api.gather_data(cards_to_gather)
            api.close()

            state.listings_df = parse_raw_data(raw_data, state.listings_df)

            # Save listings
            export_name = args.export
            save_listings(state.listings_df, export_name)

        except Exception as e:
            print_error(f"Error during gathering: {str(e)}")
            sys.exit(1)

    # Find cheapest sellers
    if args.find_cheapest:
        if not state.desired_cards:
            print_error("Cannot find cheapest without card list. Use --cards option.")
            sys.exit(1)

        if state.listings_df.empty:
            print_error("Cannot find cheapest without listings. Use --listings or --gather option.")
            sys.exit(1)

        try:
            card_names = [card.lower() for card in state.desired_cards]

            # Create and filter sellers dataframe
            sellers_df, found_cards = create_sellers_dataframe(state.listings_df, card_names)
            filtered_df = filter_sellers_df(sellers_df, found_cards)

            # Load or fetch shipping dictionary
            if state.shipping_dict is None:
                print_info(f"Fetching shipping prices for {state.to_country}...")
                state.shipping_dict = ShippingApi.get_shipping_prices(state.to_country)

                # Cache shipping dictionary
                shipping_cache_path = os.path.join(os.path.dirname(__file__), "shipping_dict.json")
                with open(shipping_cache_path, 'w') as f:
                    json.dump(state.shipping_dict, f)

            # Find optimal groups
            desired_cards_set = set(found_cards)
            optimal_groups, min_cost = find_cheapest_seller_group(
                filtered_df, state.shipping_dict, desired_cards_set
            )

            # Output results
            output_file = None
            if args.output:
                output_file = open(args.output, 'w')

            total_card_cost = 0
            print(f"\n{Colors.BOLD}=== Results ==={Colors.RESET}")

            for seller, cards in optimal_groups.items():
                for card in cards:
                    price = filtered_df.loc[filtered_df['seller'] == seller, card].values[0]
                    link_values = state.listings_df.loc[
                        (state.listings_df['seller'] == seller) &
                        (state.listings_df['card_name'].str.lower() == card.lower()),
                        'link'
                    ].values
                    link = link_values[0] if len(link_values) > 0 else None

                    output_string = f"  - {card}: buy from {seller} at {price:.2f}€" + \
                                   (f" (link: {link})" if link else "")
                    print(output_string)
                    if output_file:
                        output_file.write(output_string + "\n")
                    total_card_cost += price

            summary = f"\nTotal card cost: {total_card_cost:.2f}€\nTotal with shipping: {min_cost:.2f}€"
            print(summary)
            if output_file:
                output_file.write(summary + "\n")
                output_file.close()
                print_success(f"Results written to {args.output}")

        except Exception as e:
            print_error(f"Error finding cheapest sellers: {str(e)}")
            print_error(traceback.format_exc())
            sys.exit(1)


if __name__ == "__main__":
    main()
