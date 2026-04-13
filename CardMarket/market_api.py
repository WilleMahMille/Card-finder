from enum import Enum
import json
import math
import time
import random
import re
import requests
from playwright.sync_api import sync_playwright, Page, expect
from playwright_stealth import Stealth
import readchar
import threading
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# Constants
SHIPPING_MAX_VALUE = 1000

# Enum for countries
class Countries(Enum):
   NONE = 0
   AUSTRIA = 1
   BELGIUM = 2
   BULGARIA = 3
   SWITZERLAND = 4
   CYPRUS = 5
   CZECH_REPUBLIC = 6
   GERMANY = 7
   DENMARK = 8
   ESTONIA = 9
   SPAIN = 10
   FINLAND = 11
   FRANCE = 12
   UNITED_KINGDOM = 13
   GREECE = 14
   HUNGARY = 15
   IRELAND = 16
   ITALY = 17
   LIECHTENSTEIN = 18
   LITHUANIA = 19
   LUXEMBOURG = 20
   LATVIA = 21
   MALTA = 22
   NETHERLANDS = 23
   NORWAY = 24
   POLAND = 25
   PORTUGAL = 26
   ROMANIA = 27
   SWEDEN = 28
   SINGAPORE = 29
   SLOVENIA = 30
   SLOVAKIA = 31
   CROATIA = 35
   JAPAN = 36
   ICELAND = 37


class CaptchaError(Exception):
    """Raised when a Cloudflare captcha is detected and cannot be solved."""
    pass


# Stealth configuration
STEALTH = Stealth(
    navigator_webdriver=True,
    navigator_plugins=True,
    navigator_permissions=True,
    navigator_languages=True,
    navigator_platform=True,
    navigator_vendor=True,
    navigator_user_agent=True,
    navigator_hardware_concurrency=True,
    webgl_vendor=True,
    media_codecs=True,
    hairline=True,
    iframe_content_window=True,
    navigator_languages_override=("en-US", "en"),
)


def human_delay(min_s: float = 0.8, max_s: float = 2.5, stop_event: threading.Event = None):
    """Sleep for a randomized duration that feels human.

    If stop_event is provided, checks it in short intervals so the caller
    can break out quickly when the user presses a key.
    """
    duration = random.uniform(min_s, max_s)
    if stop_event is None:
        time.sleep(duration)
        return
    end = time.monotonic() + duration
    while time.monotonic() < end:
        if stop_event.is_set():
            return
        time.sleep(min(0.1, end - time.monotonic()))


def human_mouse_move(page: Page, target_x: int, target_y: int, steps_range: tuple = (15, 30)):
    """Move the mouse to (target_x, target_y) along a curved, jittery path."""
    box = page.viewport_size
    if not box:
        return
    # Start from a random-ish current position
    cur_x = random.randint(0, box["width"])
    cur_y = random.randint(0, box["height"])
    steps = random.randint(*steps_range)

    for i in range(1, steps + 1):
        t = i / steps
        # Ease-in-out curve
        t_ease = t * t * (3 - 2 * t)
        mid_x = cur_x + (target_x - cur_x) * t_ease + random.gauss(0, 2)
        mid_y = cur_y + (target_y - cur_y) * t_ease + random.gauss(0, 2)
        page.mouse.move(mid_x, mid_y)
        time.sleep(random.uniform(0.005, 0.02))


def human_scroll(page: Page, direction: str = "down"):
    """Scroll the page like a human — variable distance with pauses."""
    distance = random.randint(200, 600)
    if direction == "up":
        distance = -distance
    steps = random.randint(3, 6)
    per_step = distance / steps
    for _ in range(steps):
        page.mouse.wheel(0, per_step + random.gauss(0, 10))
        time.sleep(random.uniform(0.05, 0.15))


# Stop event handler for active mode
def input_reader_thread_with_readchar(stop_event):
    while not stop_event.is_set():
        try:
            char = readchar.readchar()
            if char:
                print(f"Received input: {char}, setting stop event")
                stop_event.set()
            time.sleep(0.1)
        except EOFError:
            print("EOFError, setting stop event")
            stop_event.set()
            break
        except Exception as e:
            print(f"Exception: {e}, setting stop event")
            stop_event.set()
            break


class ShippingApi:
    """A utility class for fetching and processing shipping prices from CardMarket."""
    
    @staticmethod
    def _parse_price_string(price_str: str) -> float | None:
        """Converts price strings like '25,00 €' or '1.234,56 €' to float using regex."""
        
        # Normalize: remove currency symbols and leading/trailing whitespace.
        # Prioritizing Euro as per user context, but also handling common symbols.
        text = price_str.replace('€', '').replace('EUR', '').strip()

        # Pattern 1: European format (comma as decimal, optional dots as thousands)
        # Examples: "1.234,56", "1234,56", "25,00"
        euro_pattern = r'(\d{1,3}(?:\.\d{3})*,\d+)|(\d+,\d+)'\

        euro_match = re.search(euro_pattern, text)
        if euro_match:
            num_str = euro_match.group(0)
            standard_format_num_str = num_str.replace('.', '').replace(',', '.')
            try:
                return float(standard_format_num_str)
            except ValueError:
                pass
        return None
    
    @staticmethod
    def _fetch_one_shipping_route(from_country_code: int, to_country_code: int, max_value: int = SHIPPING_MAX_VALUE) -> dict | None:
        """Fetches and returns the cheapest valid shipping option for one route using requests."""
        api_url = "https://help.cardmarket.com/api/shippingCosts"
        params = {
            'locale': 'en',
            'fromCountry': from_country_code,
            'toCountry': to_country_code,
            'preview': 'false',
        }

        try:
            response = requests.get(api_url, params=params, timeout=150)
            response.raise_for_status()
            
            shipping_options_data = response.json()
            if not isinstance(shipping_options_data, list):
                return None

            valid_options = []
            
            for option in shipping_options_data:
                option_max_value_str = option.get('maxValue')
                option_price_str = option.get('price')

                parsed_max_value = ShippingApi._parse_price_string(option_max_value_str)
                parsed_price = ShippingApi._parse_price_string(option_price_str)

                if parsed_max_value is not None and parsed_price is not None:
                    if parsed_max_value < max_value:
                        temp_option = {
                            "price": parsed_price,
                            "maxValue": parsed_max_value,
                        }
                        valid_options.append(temp_option)
                    else:
                        return valid_options
            return valid_options
        except requests.exceptions.RequestException as e:
            print(f"API request failed for route {from_country_code}->{to_country_code}: {e}")
            return None
        except json.JSONDecodeError:
            print(f"Failed to decode JSON response for route {from_country_code}->{to_country_code}")
            return None

    @staticmethod
    def get_shipping_prices(to_country: str = "SWEDEN", max_value: int = SHIPPING_MAX_VALUE) -> dict:
        """
        Fetches shipping prices from all countries in Enum to the target_to_country_code.
        Uses _fetch_one_shipping_route for each pair.
        """
        target_to_country_code = Countries[to_country.upper()].value
        print(f"Starting to fetch shipping prices from all origins to {Countries(target_to_country_code).name}...")
        all_shipping_prices_data = {}
        
        for from_country_enum_member in Countries:
            if from_country_enum_member == Countries.NONE:
                continue
            
            from_country_name_log = from_country_enum_member.name
            print(f"  Fetching for: {from_country_name_log} -> {Countries(target_to_country_code).name}")
            
            valid_shipping_options = ShippingApi._fetch_one_shipping_route(from_country_enum_member.value, target_to_country_code, max_value)
            
            if valid_shipping_options:
                all_shipping_prices_data[from_country_enum_member.name] = valid_shipping_options
            else:
                all_shipping_prices_data[from_country_enum_member.name] = {
                    "error": f"No suitable shipping option found for items <= {max_value} EUR"
                }
            
            time.sleep(0.33) # Be polite to the API - ~3 requests per second max

        print(f"Finished fetching all shipping prices to {Countries(target_to_country_code).name}.")
        return all_shipping_prices_data



class CardApi:
    def __init__(self, language: str = "English", headless: bool = False):
        """Initialize the API with Playwright."""
        print("Initializing CardMarket API with Playwright...")
        self.base_url = "https://www.cardmarket.com/en/Magic"
        self.listings_data = {}
        self.language = language.lower()
        self.headless = headless
        self._start_playwright()

    def _start_playwright(self):
        """Initialize Playwright and the browser with stealth evasions."""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.firefox.launch(headless=self.headless)
        self.context = self.browser.new_context(
            viewport={"width": random.randint(1200, 1400), "height": random.randint(800, 950)},
            locale="en-US",
        )
        STEALTH.apply_stealth_sync(self.context)
        self.page = self.context.new_page()
        
        # Set up URL modification
        self._setup_url_modifier()
        
        # Navigate to the base URL
        self.page.goto(self.base_url)
        self._wait_for_captcha()

    def _is_captcha_page(self) -> bool:
        """Check if the current page is a Cloudflare challenge/captcha."""
        title = self.page.title()
        if "just a moment" in title.lower():
            return True
        turnstile = self.page.query_selector("input[name='cf-turnstile-response']")
        if turnstile:
            return True
        challenge = self.page.query_selector("#challenge-form, #cf-challenge-running")
        if challenge:
            return True
        return False

    def _wait_for_captcha(self, timeout_s: int = 300) -> bool:
        """If a captcha is detected, wait for it to be resolved.

        In non-headless mode: pauses and polls until the user solves it.
        In headless mode: logs an error and raises an exception since
        there is no browser window for the user to interact with.

        Returns True if captcha was detected (and resolved), False if no captcha.
        """
        if not self._is_captcha_page():
            return False

        if self.headless:
            print("[CAPTCHA] Cloudflare challenge detected in headless mode.")
            print("[CAPTCHA] Cannot solve automatically. Stopping.")
            raise CaptchaError(
                "Cloudflare captcha detected in headless mode. "
                "Re-run without --headless to solve it manually."
            )

        print("[CAPTCHA] Cloudflare challenge detected!")
        print("[CAPTCHA] Please solve it in the browser window...")

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            time.sleep(1)
            if not self._is_captcha_page():
                print("[CAPTCHA] Solved! Continuing...")
                human_delay(1.0, 2.0)
                return True

        print(f"[CAPTCHA] Timed out after {timeout_s}s waiting for captcha to be solved.")
        raise CaptchaError(f"Captcha not solved within {timeout_s} seconds.")

    def _navigate(self, url: str, **kwargs):
        """Navigate to a URL and check for captcha afterwards."""
        kwargs.setdefault("timeout", 60000)
        self.page.goto(url, **kwargs)
        self._wait_for_captcha()

    def _setup_url_modifier(self):
        """Set up the route handler to modify URLs based on patterns."""
        def route_handler(route):
            url = route.request.url
            modified_url = self._modify_url(url)
            
            if modified_url != url:
                route.continue_(url=modified_url)
            else:
                route.continue_()
        
        # Apply the route handler to all URLs
        self.page.route("**/*", route_handler)

    def _modify_url(self, url):
        """Modify URL based on patterns."""
        # Check if this is a product singles page URL
        if "/Products/Singles/" in url:
            # Parse the URL
            parsed_url = urlparse(url)
            
            # Get existing query parameters
            query_params = parse_qs(parsed_url.query)
            
            # Add our parameters if they don't exist
            modified = False
            if "sellerType" not in query_params:
                query_params["sellerType"] = ["1,2"]  # Professional sellers
                modified = True
            if "language" not in query_params:
                query_params["language"] = ["1"]      # English cards
                modified = True
            if "minCondition" not in query_params:
                query_params["minCondition"] = ["2"]
                modified = True
            
            if modified:
                # Rebuild the query string
                new_query = urlencode(query_params, doseq=True)
                
                # Create new parsed result with updated query
                new_parsed = parsed_url._replace(query=new_query)
                
                # Return the modified URL
                return urlunparse(new_parsed)
        
        return url


    def parse_price(self, price_text):
        """Parse price string like '25,00 €' to float."""
        # Remove currency symbols and whitespace
        text = price_text.replace('€', '').replace('EUR', '').strip()
        
        # Match European format with comma as decimal separator
        euro_pattern = r'(\d{1,3}(?:\.\d{3})*,\d+)|(\d+,\d+)'
        euro_match = re.search(euro_pattern, text)
        
        if euro_match:
            num_str = euro_match.group(0)
            # Convert to standard float format
            standard_format = num_str.replace('.', '').replace(',', '.')
            try:
                return float(standard_format)
            except ValueError:
                pass
                
        return None
    
    def parse_country(self, location_text):
        """Extract country from location text like 'Item location: Germany'."""
        if location_text and ":" in location_text:
            try:
                return location_text.split(":")[1].strip()
            except IndexError:
                pass
        return "Unknown"
    
    def _collect_listings(self):
        """
        Collects all listings that are currently on the page.
        """
        current_url = self.page.url

        # First we make sure we are on a listings page.
        if '/Products/Singles/' not in current_url and '/Offers/Singles/' not in current_url:
            return None

        try:
            # Wait for listings to load
            article_rows_selector = "div[id^='articleRow']"
            self.page.wait_for_selector(article_rows_selector, timeout=3000)

            # Simulate reading the page — scroll down through listings
            human_delay(0.5, 1.2)
            for _ in range(random.randint(1, 3)):
                human_scroll(self.page, "down")
                human_delay(0.3, 0.8)

            # Find and process all listing rows
            article_elements = self.page.query_selector_all(article_rows_selector)
            article_count = len(article_elements)
            print(f"Found {article_count} listings on current page.")
            new_listings = []
            
            for row_element in article_elements:
                # Extract card name
                card_name = None
                card_name_element = row_element.query_selector("a[href*='/Products/Singles/']")
                if card_name_element:
                    card_name = card_name_element.text_content().strip()

                if not card_name:
                    card_name = self.page.url.split("?")[0].split("/")[-1].replace("-", " ").replace("_", " ")
                    
                if '/Products/Singles/' in current_url:
                    # Extract seller name
                    seller_element = row_element.query_selector("div.col-sellerProductInfo span.seller-name a[href*='/Users/']")
                    if not seller_element:
                        print(f"No seller element found for {card_name}")
                        continue
                    seller_name = seller_element.text_content().strip()
                elif '/Users/' in current_url and '/Offers/Singles/' in current_url:
                    seller_name = self.page.url.split("/")[-3]
                
                # Extract price
                price_element = row_element.query_selector("div.price-container span")
                
                if not price_element:
                    print(f"No price element found for {card_name}")
                    continue
                
                price_text = price_element.text_content().strip()
                price = self.parse_price(price_text)
                
                # Extract language
                language = "Unknown"
                language_element = row_element.query_selector("div.product-attributes span.icon[aria-label]")
                if language_element:
                    language = language_element.get_attribute('aria-label') or ""
                    if not language:
                        language = language_element.get_attribute('data-original-title') or "Unknown"
                
                if language.lower() != self.language:
                    print(f"Language mismatch for {card_name}: {language} != {self.language}")
                    continue

                # Extract country
                country = "Unknown"
                location_element = row_element.query_selector("span.seller-info span[aria-label^='Item location:'][data-bs-toggle='tooltip']")
                if location_element:
                    location_text = location_element.get_attribute('aria-label') or ""
                    country = self.parse_country(location_text)
                else:
                    # Try alternative format
                    alt_location_element = row_element.query_selector("span.seller-info span[data-bs-original-title^='Item location:'][data-bs-toggle='tooltip']")
                    if alt_location_element:
                        location_text = alt_location_element.get_attribute('data-bs-original-title') or ""
                        country = self.parse_country(location_text)
                
                new_listing = {
                    "price": price,
                    "country": country,
                    "link": current_url
                }
                
                if card_name not in self.listings_data:
                    self.listings_data[card_name] = {}
                new_listings.append(new_listing)
                self.listings_data[card_name][seller_name] = new_listing
            
            return self.listings_data
                
        except Exception as e:
            print(f"Error gathering data: {e}")
            return None
    
    def _parse_card_name_search(self, card_name: str):
        """
        Parses a card name to a format that can be used for searching.
        """
        return card_name.lower().replace(" ", "+").replace("'", "%27").replace(",", "")
    
    def _parse_card_name_dict(self, card_name: str):
        """
        Parses a found card name and an inputed card name to the same format.
        """
        return card_name.lower().replace(" ", "").replace("'", "").replace(',', '').replace('-', '')

    def _get_unscraped_cards(self, card_names: list[str]):
        """
        Returns a list of cards that have not been scraped yet.
        """
        unscraped_cards = card_names.copy()
        indices_to_remove = []
        
        for scraped_card in self.listings_data.keys():
            for index, card_name in enumerate(card_names):
                parsed_card_name = self._parse_card_name_dict(card_name)
                parsed_scraped_card = self._parse_card_name_dict(scraped_card)
                if parsed_scraped_card.startswith(parsed_card_name):
                    # Scraped card
                    indices_to_remove.append(index)
                    break
        
        for index in reversed(indices_to_remove):
            unscraped_cards.pop(index)

        print(f"Number of unscraped cards: {len(unscraped_cards)}")
        print(f"unscraped cards: {unscraped_cards}")
        return unscraped_cards

    def _search_card(self, card_name: str):
        """
        Searches for a card and returns a list of listings.
        """
        # base url for searching cards (mode=list preserves the list view with productRow divs)
        base_url = "https://www.cardmarket.com/en/Magic/Products/Search?mode=list&searchString="

        # Search for the card
        search_url = f"{base_url}{self._parse_card_name_search(card_name)}"
        self._navigate(search_url)
        human_delay(1.0, 2.5)

        # This will either redirect us to a product page, or present a list of results.
        # We first check if we are redirected to a product page.
        current_url = self.page.url
        if current_url != search_url and "/Products/Singles/" in current_url:
            self._navigate(self._modify_url(current_url))
            human_delay(0.8, 1.5)
            return self._collect_listings()

        # If we are not redirected, we need to check if there are any results.
        no_results = self.page.get_by_text("Sorry, no matches for your query")
        if no_results.count() > 0:
            print(f"No results found for {card_name}")
            return []

        # Try list-view product rows first, fall back to grid-view links
        product_links = self._find_product_links(card_name)
        if not product_links:
            print(f"Could not find products with the name {card_name}")
            return []

        # Navigate to the first matching product
        for link_element in product_links:
            box = link_element.bounding_box()
            if box:
                human_mouse_move(
                    self.page,
                    int(box["x"] + box["width"] / 2),
                    int(box["y"] + box["height"] / 2),
                )
                human_delay(0.2, 0.5)

            link_element.click()
            self.page.wait_for_load_state("networkidle")
            self._wait_for_captcha()
            human_delay(0.8, 1.8)
            return self._collect_listings()

        print(f"Could not find products with the name {card_name}")
        return []

    def _find_product_links(self, card_name: str) -> list:
        """Find product links on a search results page.

        Tries list-view (productRow divs) first, then falls back to
        the grid-view (direct product links with images).
        """
        # List view: div[id^='productRow']
        product_selector = "div[id^='productRow']"
        try:
            self.page.wait_for_selector(product_selector, timeout=3000)
            product_elements = self.page.query_selector_all(product_selector)
            matches = []
            for product_element in product_elements:
                link_element = product_element.query_selector("a[href*='/Products/']")
                if not link_element:
                    continue
                name_text = link_element.text_content().strip()
                if card_name.lower() in name_text.lower():
                    matches.append(link_element)
            if matches:
                return matches
        except Exception:
            pass

        # Grid view fallback: links with product images
        grid_links = self.page.query_selector_all("a[href*='/Products/Singles/']")
        matches = []
        for link in grid_links:
            img = link.query_selector("img[alt]")
            if img:
                alt = img.get_attribute("alt") or ""
                if card_name.lower() in alt.lower():
                    matches.append(link)
                    continue
            link_text = link.text_content().strip()
            if card_name.lower() in link_text.lower():
                matches.append(link)
        return matches

    def gather_data(self, card_names: list[str], max_automatic_errors: int = 7):
        """
        Has two modes for gathering data:
        - Active mode, where it will search for each card and collect listings
        - Passive mode, where it will only collect listings from the current page.
        """
        active_mode = False
        self._stop_event = threading.Event()
        self._stop_event.set()

        cards_to_scrape = card_names
        while True:
            print("--------------------------------")
            print("Please enter one of the following options:")
            print("'s' to save and quit")
            print("'a' to start automatic mode")
            print("'p' to toggle passive data gathering mode")
            print("'r' to restart the browser")
            action = input()
            if action == 's':
                return self._format_listings(card_names)
            elif action == 'a':
                cards_to_scrape = self._get_unscraped_cards(card_names)
                self._stop_event.clear()
                active_mode = True
            elif action == 'p':
                self._stop_event.clear()
                active_mode = False
            elif action == 'r':
                self.close()
                self._start_playwright()
                cards_to_scrape = self._get_unscraped_cards(card_names)
                continue
            else:
                print("Invalid option, please try again")
                continue

            input_thread = threading.Thread(
                target=input_reader_thread_with_readchar,
                args=(self._stop_event,),
                daemon=True,
            )
            input_thread.start()
            print(f"{'Automatic mode' if active_mode else 'Passive mode'}, press any key to return to the menu")

            previous_content = self.page.content()
            automatic_error_count = 0

            while not self._stop_event.is_set():
                if active_mode:
                    zero_listings_count = 0
                    for card_name in cards_to_scrape:
                        if self._stop_event.is_set():
                            break
                        try:
                            listings = self._search_card(card_name)
                            if listings:
                                self.listings_data.update(listings)
                                zero_listings_count = 0
                            else:
                                zero_listings_count += 1
                                print(f"No listings found for {card_name}")
                                if zero_listings_count > 1:
                                    print(f"Multiple cards with no listings, restarting browser")
                                    self.close()
                                    self._start_playwright()
                                    cards_to_scrape = self._get_unscraped_cards(card_names)
                                    break
                        except CaptchaError:
                            # In headless mode this is fatal — save what we have
                            if self.headless:
                                print("[CAPTCHA] Returning collected data.")
                                return self._format_listings(card_names)
                            # In non-headless mode _wait_for_captcha already
                            # paused for the user to solve it, so just retry
                            cards_to_scrape = self._get_unscraped_cards(card_names)
                            break
                        except Exception as e:
                            print(f"Error gathering data, trying restarting browser")
                            self.close()
                            self._start_playwright()
                            cards_to_scrape = self._get_unscraped_cards(card_names)
                            if automatic_error_count > max_automatic_errors:
                                print(f"Quitting after getting {automatic_error_count} errors")
                                return self._format_listings(card_names)
                            automatic_error_count += 1
                            break

                        human_delay(2.0, 5.0, self._stop_event)
                    print("--------------------------------")
                    cards_to_scrape = self._get_unscraped_cards(card_names)
                    if len(cards_to_scrape) == 0:
                        print("No more cards to scrape, returning to menu")
                        break

                else:
                    if self._stop_event.wait(0.5):
                        break
                    try:
                        current_content = self.page.content()
                        if previous_content != current_content:
                            self._collect_listings()
                        previous_content = current_content
                    except Exception as e:
                        print(f"Error gathering data: {e}")
    
    def _format_listings(self, card_names):
        """Formats the listings data into a list of dictionaries."""
        listings = []
        for parsed_card_name, sellers in self.listings_data.items():
            for seller, data in sellers.items():
                unparsed_card_name = None
                for original_card_name in card_names:
                    if self._parse_card_name_dict(original_card_name) == self._parse_card_name_dict(parsed_card_name):
                        unparsed_card_name = original_card_name
                        break

                if not unparsed_card_name:
                    print(f"Warning: No unparsed card name found for {parsed_card_name}")
                listings.append({
                    "seller": seller,
                    "card_name": unparsed_card_name,
                    "price": data["price"],
                    "country": data["country"],
                    "link": data["link"]
                })
        return listings
    
    def close(self):
        """Close the browser and Playwright."""
        if hasattr(self, 'browser') and self.browser:
            print("Closing browser...")
            self.browser.close()
        
        if hasattr(self, 'playwright') and self.playwright:
            print("Stopping Playwright...")
            self.playwright.stop()


# Example usage:
if __name__ == "__main__":
    scraper = CardApi()
    try:
        # Example: Search for a specific card
        card_names = ["Black Lotus", "Goldspan Dragon"]
        scraper.gather_data(card_names)
    finally:
        scraper.close() 