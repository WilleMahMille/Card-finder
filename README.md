# Card finder

This script helps you find the cheapest way to purchase magic the gathering cards by first gathering listings / data, and then using a dynamic programming approach to identify the cheapest way to purchase the cards, taking shipping prices into consideration.

## API specifications

This section explains the interface requirements for each API type that you need to implement. The main script expects two APIs: the Shipping API and the Card API.

### Shipping API

The Shipping API must provide functionality to fetch shipping cost information. This data is essential for calculating the total cost of purchasing cards from different countries.

#### Required Interface

Your Shipping API implementation must provide the following static method:

##### `ShippingApi.get_shipping_prices(to_country: str, max_value: int) -> dict`

**Purpose**: Fetches shipping prices from all available countries to a specified destination country.

**Parameters**:

- `to_country` (str): The destination country name. Must match a country name from your Countries enum (case-insensitive).
- `max_value` (int): The maximum card value threshold for filtering shipping options. Only shipping options with maxValue less than this threshold should be included.

**Returns**:

- `dict`: A dictionary where keys are country names (matching your Countries enum) and values are either:
  - A list of valid shipping options (each containing `price` and `maxValue` fields). The `price` field is how much the shipping costs and the `maxValue` field is how expensive the cards can be for that shipping option. The list should be sorted with the first element having the cheapest `maxValue`.
  - An error object with an error message if no suitable shipping options are found

**Example Return Structure**:

```python
{
    "AUSTRIA": [
        {"price": 2.50, "maxValue": 50.0},
        {"price": 5.00, "maxValue": 99.99}
    ],
    "BELGIUM": [
        {"price": 3.00, "maxValue": 75.0}
    ],
    "FRANCE": {
        "error": "No suitable shipping option found for items <= 50 EUR"
    }
}
```

#### Implementation Requirements

- **Sorting**: Return shipping options sorted by `maxValue` (cheapest first)

### Card API

The Card API provides functionality to scrape and gather card listing data from card marketplaces.

#### Required Interface

Your Card API implementation must provide the following methods:

##### `CardApi.__init__(language: str = "English")`

**Purpose**: Initialize the API with the specified language preference.

**Parameters**:

- `language` (str, optional): The preferred language for card listings. Defaults to "English".

##### `CardApi.gather_data(card_names: list[str]) -> list[dict]`

**Purpose**: Scrapes card listings for the specified card names.

**Parameters**:

- `card_names` (list[str]): List of card names to search for and gather data on.

**Returns**:

- `list[dict]`: A list of dictionaries, where each dictionary represents a card listing with the following required keys:
  - `seller` (str): The name/identifier of the seller
  - `card_name` (str): The name of the card
  - `price` (float): The price of the card
  - `country` (str): The country where the seller is located
  - `link` (str): A link to the listing (for reference)

**Example Return Structure**:

```python
[
    {
        "seller": "CardShop123",
        "card_name": "Black Lotus",
        "price": 25000.00,
        "country": "Germany",
        "link": "https://example.com/listing/123"
    },
    {
        "seller": "MagicCards4U",
        "card_name": "Lightning Bolt",
        "price": 0.50,
        "country": "France",
        "link": "https://example.com/listing/456"
    }
]
```

##### `CardApi.close()`

**Purpose**: Clean up any resources (browsers, connections, etc.) used by the API.

#### Implementation Requirements

- **Language Filtering**: Filter results to match the specified language preference
- **Price Parsing**: Convert price strings to float values
- **Country Extraction**: Extract and normalize country information from listings
- **Error Handling**: Handle missing listings, network errors, and parsing failures gracefully
- **Resource Management**: Properly clean up resources in the `close()` method
- **Duplicate Handling**: Handle duplicate listings appropriately

#### Usage Pattern

The main script expects to use your Card API as follows:

```python
api = CardApi(language="English")
try:
    listings = api.gather_data(["Black Lotus", "Lightning Bolt"])
    # Process listings...
finally:
    api.close()
```

## Usage

Once you have implemented both APIs according to the specifications above, you can use the main script:

```bash
# Scrape card data
python main.py --scrape --listings-path listings.csv

# Find cheapest purchasing strategy
python main.py --find-cheapest --listings-path listings.csv --shipping-dict-path shipping.json

# Both scrape and analyze
python main.py --scrape --find-cheapest --listings-path listings.csv --shipping-dict-path shipping.json --output results.txt
```

## Configuration

Edit the `DESIRED_CARDS` list in `main.py` to specify which cards you want to find the cheapest purchasing strategy for. You can also modify other configuration variables like `TO_COUNTRY` and `LANGUAGE` as needed.
