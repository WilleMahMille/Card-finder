import pandas as pd
import argparse
import json
import ast
from scraper import parse_to_dataframe, search_sets_for_tradable_cards
from tqdm import tqdm

def load_cards_from_file(file_path: str):
  df = pd.read_csv(file_path)
  return df

def match_cards(owned_cards: pd.DataFrame, tradable_cards: pd.DataFrame):
  # This funciton will match the cards from the owned_cards and tradable_cards dataframes, and will return a dataframe with the matched cards.
  # The dataframe will have the following columns:
  # - card_name
  # - tradable_card_price
  # - tradable_card_quantity
  
  # Use a list to collect rows - much more efficient than repeated pd.concat
  matched_rows = []
  
  for index, row in tqdm(tradable_cards.iterrows(), total=len(tradable_cards), desc="Matching cards"):
    card_name = row["name"]
    card_set = row["set"]
    trade_price = row["trade_in_price"]
    trade_quantity = row["max_cards"]
    card_qualities = row["qualities"]
    
    # Handle case where card_qualities might be a string (JSON) or already a dict
    if isinstance(card_qualities, str):
        try:
            card_qualities = ast.literal_eval(card_qualities)
        except (ValueError, SyntaxError) as e:
            print(f"Failed to parse qualities as Python dict: {card_qualities}")
            print(f"Error: {e}")
            # Set default values if parsing fails
            card_qualities = {"foil": False}
    
    is_foil = card_qualities.get('foil')
    

    # Filter owned cards by name, set, and foil status
    matching_owned_cards = owned_cards[
        (owned_cards["Name"].fillna("").str.lower().str.strip() == card_name.lower().strip()) &
        (owned_cards["Set name"].fillna("").str.lower().str.strip() == card_set.lower().strip()) &
        (owned_cards["Foil"].fillna("normal").str.lower().str.strip() == ("foil" if is_foil else "normal"))
    ]
    if not matching_owned_cards.empty:
      max_tradable = min(trade_quantity, matching_owned_cards["Quantity"].sum())
      
      # Append to list instead of using pd.concat
      matched_rows.append({
          "card_name": card_name, 
          "tradable_card_price": trade_price, 
          "tradable_card_quantity": max_tradable,
          "qualities": card_qualities,
          "card_set": card_set
      })

  # Create DataFrame once from the list of dictionaries
  matched_cards = pd.DataFrame(matched_rows)
  matched_cards = matched_cards.sort_values(by="tradable_card_price")

  return matched_cards




def arg_parser():
  parser = argparse.ArgumentParser()
  parser.add_argument("--owned-cards", type=str, required=True)
  parser.add_argument("--tradable-cards", type=str, required=False)
  parser.add_argument("--output-file", type=str, required=False, default="matched_cards.csv")
  return parser.parse_args()

def main():
  args = arg_parser()
  owned_cards = load_cards_from_file(args.owned_cards)
  if args.tradable_cards:
    tradable_cards = load_cards_from_file(args.tradable_cards)
  else:
    BASE_URL = "https://old.dragonslair.se/category/444/loskort"
    tradable_cards = search_sets_for_tradable_cards(BASE_URL)
    tradable_cards = parse_to_dataframe(tradable_cards)
    tradable_cards.to_csv("tradable_cards.csv", index=False)

  matched_cards = match_cards(owned_cards, tradable_cards)
  matched_cards.to_csv(args.output_file, index=False)
  
  total_price = 0

  for index, row in matched_cards.iterrows():
    print(f"{row['card_name']} - card set: {row['card_set']} - price: {row['tradable_card_price']} - amount: {row['tradable_card_quantity']}")
    total_price += row['tradable_card_price'] * row['tradable_card_quantity']
  print(f"Total tradeable price: {total_price}")

if __name__ == "__main__":
  main()




