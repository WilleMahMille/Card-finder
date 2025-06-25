from enum import Enum
import json
import time
import random
import re
import requests
from playwright.sync_api import sync_playwright, Page, expect
import readchar
import threading
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# Constants
SHIPPING_MAX_VALUE = 100

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
    def __init__(self, language: str = "English"):
        """Initialize the API with Playwright."""
        print("Initializing CardMarket API with Playwright...")
        self.base_url = "https://www.cardmarket.com/en/Magic"
        self.listings_data = {}
        self.language = language.lower()
        self._start_playwright()

    def _start_playwright(self):
        """Initialize Playwright and the browser."""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.firefox.launch(headless=False)
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        
        # Set up URL modification
        self._setup_url_modifier()
        
        # Navigate to the base URL
        self.page.goto(self.base_url)

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
        return card_name.lower().replace(" ", "+").replace("'", "%27")
    
    def _parse_card_name_dict(self, card_name: str):
        """
        Parses a found card name and an inputed card name to the same format.
        """
        return card_name.lower().replace(" ", "").replace("'", "")

    def _get_unscraped_cards(self, card_names: list[str]):
        """
        Returns a list of cards that have not been scraped yet.
        """
        unscraped_cards = card_names.copy()
        indices_to_remove = []
        
        for scraped_card in self.listings_data.keys():
            for index, card_name in enumerate(card_names):
                parsed_card_name = self._parse_card_name_search(card_name)
                parsed_scraped_card = self._parse_card_name_search(scraped_card)
                if parsed_scraped_card.startswith(parsed_card_name):
                    # Scraped card
                    indices_to_remove.append(index)
                    break
        for index in reversed(indices_to_remove):
            unscraped_cards.pop(index)

        print(f"Number of unscraped cards: {len(unscraped_cards)}")
        print(f"unscraped cards: {unscraped_cards}")
        print(f"scraped cards: {self.listings_data.keys()}")
        return unscraped_cards

    def _search_card(self, card_name: str):
        """
        Searches for a card and returns a list of listings. 
        """
        # base url for searching cards
        base_url = "https://www.cardmarket.com/en/Magic/Products/Search?searchString="

        # Search for the card
        search_url = f"{base_url}{self._parse_card_name_search(card_name)}"
        self.page.goto(search_url)
        
        # This will either redirect us to a product page, or present a list of results. 
        # We first check if we are redirected to a product page. 
        current_url = self.page.url
        if current_url != search_url and "/Products/Singles/" in current_url:
            self.page.goto(self._modify_url(current_url))
            return self._collect_listings()
        
        # If we are not redirected, we need to check if there are any results. 
        no_results = self.page.get_by_text("Sorry, no matches for your query")
        if no_results.count() > 0:
            print(f"No results found for {card_name}")
            return []

        # Now we need to get the links of the products. 
        product_selector = "div[id^='productRow']"
        try:
            self.page.wait_for_selector(product_selector, timeout=3000)
        except Exception:
            print(f"Timeout waiting for product elements for {card_name}")
            return []
        
        product_elements = self.page.query_selector_all(product_selector)
        
        for product_element in product_elements:
            link_element = product_element.query_selector("a[href*='/Products/']")
            if not link_element:
                continue
                
            name_text = link_element.text_content().strip()
            if card_name.lower() in name_text.lower():
                # Click the product link
                link_element.click()
                
                # Wait for navigation to complete
                self.page.wait_for_load_state("networkidle")
                
                # The URL modifier will automatically add the necessary parameters
                return self._collect_listings()
        
        # If we don't find any results, we return an empty list. 
        print(f"Could not find products with the name {card_name}")
        return []

    def gather_data(self, card_names: list[str], max_automatic_errors: int = 7):
        """
        Has two modes for gathering data:
        - Active mode, where it will search for each card and collect listings
        - Passive mode, where it will only collect listings from the current page.
        """
        active_mode = False
        stop_event = threading.Event()
        stop_event.set()

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
                # update the card names to scrape
                cards_to_scrape = self._get_unscraped_cards(card_names)
                stop_event.clear()
                active_mode = True
            elif action == 'p':
                stop_event.clear()
                active_mode = False
            elif action == 'r':
                self.close()
                self._start_playwright()
                cards_to_scrape = self._get_unscraped_cards(card_names)
                continue
            else:
                print("Invalid option, please try again")
                continue
                
            input_thread = threading.Thread(target=input_reader_thread_with_readchar, args=(stop_event,))
            input_thread.start()
            print(f"{'Automatic mode' if active_mode else 'Passive mode'}, press any key to return to the menu")

            previous_content = self.page.content()
            
            automatic_error_count = 0
            
            while not stop_event.is_set():
                if active_mode:
                    zero_listings_count = 0
                    for card_name in cards_to_scrape:
                        try: 
                            listings = self._search_card(card_name)
                            if listings:
                                self.listings_data.update(listings)
                                zero_listings_count = 0
                            else:
                                zero_listings_count += 1
                                print(f"No listings found for {card_name}")
                                if zero_listings_count > 1:
                                    print(f"Detecting captcha, restarting browser")
                                    self.close()
                                    self._start_playwright()
                                    cards_to_scrape = self._get_unscraped_cards(card_names)
                                    break
                            if stop_event.is_set():
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
                        
                        time.sleep(random.uniform(0.5, 1.5))
                    print("--------------------------------")
                    if len(cards_to_scrape) == 0:
                        print("No more cards to scrape, returning to menu")
                        break
                   
                else:
                    try:
                        current_content = self.page.content()
                        if previous_content != current_content: 
                            self._collect_listings()
                        previous_content = current_content
                    except Exception as e:
                        print(f"Error gathering data: {e}")
                    time.sleep(0.5)
    
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