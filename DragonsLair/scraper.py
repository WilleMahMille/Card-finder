import math
import time
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
from tqdm import tqdm

BASE_URL = "https://old.dragonslair.se/category/444/loskort"

def find_tradable_cards(response: requests.Response):
  soup = BeautifulSoup(response.text, "html.parser")
  
  # Find the products grid div
  products_grid = soup.find("div", class_="products grid")
  if not products_grid:
    print("Warning: Could not find div with class 'products grid'")
    print("url: ", response.url)
    return []
  
  # Find all item divs within the products grid
  card_items = products_grid.find_all("div", class_="item")

  cards = []
  for item in card_items:
    # Extract card name from div.title > a
    title_div = item.find("div", class_="title")
    if not title_div:
      continue
    
    name_link = title_div.find("a")
    if not name_link:
      continue
    
    card_name = name_link.get_text().split('(')[0].strip()

    subtitle_div = item.find("div", class_="subtitle")
    if not subtitle_div:
      continue
    
    subtitle_parts = subtitle_div.get_text().split(',')

    set_name = subtitle_parts[0].strip()

    card_qualities = {
      'borderless': False,
      'foil': False,
      'extended_art': False,
      'showcase': False,
    }

    for part in subtitle_parts[1:]:
      if part.strip() == "Foil":
        card_qualities['foil'] = True
      elif part.strip() == "Borderless":
        card_qualities['borderless'] = True
      elif part.strip() == "Extended Art":
        card_qualities['extended_art'] = True
      elif part.strip() == "Showcase":
        card_qualities['showcase'] = True
    
    # Extract buyin information from div.buyin
    buyin_div = item.find("div", class_="buyin")
    if not buyin_div:
      continue
    
    # Find the text after the i element
    buyin_text = buyin_div.get_text()
    
    # Use regex to extract price and quantity information
    # Pattern matches: "number kr (Fullt)" or "number kr (Max number st)"
    price_pattern = r'(\d+)\s*kr\s*\((.*?)\)'
    match = re.search(price_pattern, buyin_text)
    
    if not match:
      print(f"Warning: Could not parse buyin text '{buyin_text}' for card '{card_name}'")
      continue
    
    price = int(match.group(1))
    quantity_info = match.group(2).strip()
    
    # Parse quantity information
    if quantity_info == "Fullt":
      max_cards = None  # Unlimited
    elif quantity_info.startswith("Max"):
      # Extract number from "Max X st"
      max_match = re.search(r'Max\s+(\d+)\s+st', quantity_info)
      if max_match:
        max_cards = int(max_match.group(1))
      else:
        print(f"Warning: Could not parse max quantity '{quantity_info}' for card '{card_name}'")
        max_cards = None
    else:
      print(f"Warning: Unknown quantity format '{quantity_info}' for card '{card_name}'")
      max_cards = None

    if max_cards is not None:
      cards.append({
        'name': card_name,
        'set': set_name,
        'trade_in_price': price,
        'max_cards': max_cards,
        'qualities': card_qualities,
      })
  
  return cards


def search_sets_for_tradable_cards(url:str, num_cards:int=-1):
  set_names = get_sets(url)
  cards = []

  for set_name, page_count in tqdm(set_names, desc="Searching sets"):
    set_name = set_name.replace(" ", "-").lower()
    if len(cards) >= num_cards and num_cards != -1:
      break
    try:
      for page in tqdm(range(1, page_count + 1), desc="Searching pages", leave=False):

        response = requests.get(f"{url}/magic-{set_name}/{page}", timeout=30)
        cards.extend(find_tradable_cards(response))
        time.sleep(0.01)
    except requests.exceptions.ConnectionError as e:
      print(f"Warning: Could not connect to {url}/magic-{set_name}".lower())
      print(e)
      continue
  cards = cards[:num_cards]
  return cards

def get_sets(url: str):
  response = requests.get(url)
  soup = BeautifulSoup(response.text, "html.parser")
  
  # Find the div with id="tag-group-9"
  tag_group_div = soup.find("div", id="tag-group-9")
  if not tag_group_div:
    print("Warning: Could not find div with id 'tag-group-9'")
    return []
  
  # Find the ul element within the div
  ul_element = tag_group_div.find("ul")
  if not ul_element:
    print("Warning: Could not find ul element within tag-group-9 div")
    return []
  
  # Find all li elements within the ul
  li_elements = ul_element.find_all("li")
  
  sets = []
  for li in li_elements:
    # Find the a element within each li
    a_element = li.find("a")
    if not a_element:
      continue
    
    # Get the title attribute and text content
    title = a_element.get("title", "").strip()
    text = a_element.get_text().strip()
    
    # Check if title and text match
    if title != text:
      print(f"Warning: Title '{title}' does not match text '{text}' for set")
    
    # Add the set name to our list (using text as the primary source)
    if text:
      set_size = li.find("small").text.strip().replace("(", "").replace(")", "")
      page_count = math.ceil(float(set_size) / 36)
      sets.append((text, page_count))

  return sets

def parse_to_dataframe(cards: list[dict]):
  df = pd.DataFrame(cards)
  return df









