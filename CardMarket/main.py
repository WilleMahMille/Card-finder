import hashlib
import json
import os
import tqdm
from market_api import CardApi, ShippingApi
from collections import defaultdict
import pandas as pd
import argparse 
import numpy as np



# --- Configuration ---

DESIRED_CARDS = [
    "Fblthp, Lost on the Range",
    "Accorder's Shield",
    "Aether Barrier",
    "Aetherflux Reservoir",
    "Ancestral Vision",
    "Arcane Signet",
    "Bone Saw",
    "Brainstorm",
    "Buried Ruin",
    "Cathar's Shield",
    "Claws of Gix",
    "Codex Shredder",
    "Counterspell",
    "Cursed Totem",
    "Dark Sphere",
    "Darksteel Relic",
    "Decanter of Endless Water",
    "Dig Through Time",
    "Dreamscape Artist",
    "Dress Down",
    "Etherium Sculptor",
    "Everflowing Chalice",
    "Eye of Ramos",
    "Fabricate",
    "Fellwar Stone",
    "Fog Bank",
    "Fountain of Youth",
    "Gilded Lotus",
    "Helm of Awakening",
    "Herbal Poultice",
    "High Tide",
    "Index",
    "Inevitable Betrayal",
    "Kite Shield",
    "Kuldotha Forgemaster",
    "Lantern of Insight",
    "Lotus Bloom",
    "Loyal Inventor",
    "Mind Stone",
    "Minds Aglow",
    "Mishra's Bauble",
    "Misleading Signpost",
    "Mystic Sanctuary",
    "Narset, Parter of Veils",
    "Obsessive Search",
    "Ornithopter",
    "Paradise Mantle",
    "Phyrexian Walker",
    "Ponder",
    "Preordain",
    "Propaganda",
    "Pyramid of the Pantheon",
    "Reliquary Tower",
    "Reshape",
    "Retract",
    "Search for Azcanta // Azcanta, the Sunken Ruin",
    "Sol Ring",
    "Sol Talisman",
    "Spell Pierce",
    "Spellbook",
    "Spidersilk Net",
    "Springleaf Drum",
    "Stonecoil Serpent",
    "The Reality Chip",
    "Thought Vessel",
    "Thran Dynamo",
    "Tormod's Crypt",
    "Transmutation Font",
    "Triton Wavebreaker",
    "Welding Jar",
    "Whispers of the Muse",
    "Winter Moon",
    "Zuran Orb"
]

# List of card names you want to acquire
sliver_DESIRED_CARDS = [
    "Sliver Overlord",
    "Amoeboid Changeling",
    "Ancient Ziggurat",
    "Arcane Sanctum",
    "Arcane Signet",
    "Assassin's Trophy",
    "Basal Sliver",
    "Birds of Paradise",
    "Bloom Tender",
    "Bonescythe Sliver",
    "Brainstorm",
    "Bristling Backwoods",
    "Canopy Vista",
    "Carpet of Flowers",
    "Chromatic Lantern",
    "City of Brass",
    "Cloudshredder Sliver",
    "Coat of Arms",
    "Command Tower",
    "Counterspell",
    "Credit Voucher",
    "Crumbling Necropolis",
    "Crypt Sliver",
    "Cryptolith Rite",
    "Crystalline Sliver",
    "Darkmoss Bridge",
    "Delay",
    "Diffusion Sliver",
    "Door of Destinies",
    "Eladamri's Call",
    "Eldritch Evolution",
    "Exotic Orchard",
    "Farseek",
    "Fellwar Stone",
    "Fleshwrither",
    "Flusterstorm",
    "Forbidden Orchard",
    "Frontier Bivouac",
    "Galerider Sliver",
    "Gemhide Sliver",
    "Harmonic Sliver",
    "Hatchery Sliver",
    "Heart Sliver",
    "Hibernation Sliver",
    "Holdout Settlement",
    "Homing Sliver",
    "Ignoble Hierarch",
    "Jungle Shrine",
    "Kodama's Reach",
    "Lavabelly Sliver",
    "Manaweft Sliver",
    "Meteor Crater",
    "Mirage Mesa",
    "Morophon, the Boundless",
    "Mystic Monastery",
    "Nature's Claim",
    "Necrotic Sliver",
    "Neoform",
    "Night Market",
    "Nomad Outpost",
    "Opulent Palace",
    "Parallel Thoughts",
    "Path of Ancestry",
    "Pillar of the Paruns",
    "Pit of Offerings",
    "Rhystic Cave",
    "Rhystic Tutor",
    "Rhythm of the Wild",
    "Ringsight",
    "Root Sliver",
    "Sandsteppe Citadel",
    "Savage Lands",
    "Seaside Citadel",
    "Secluded Courtyard",
    "Sedge Sliver",
    "Sentinel Sliver",
    "Shifting Sliver",
    "Sliver Hive",
    "Sliver Hivelord",
    "Sol Ring",
    "Survivors' Encampment",
    "Swords to Plowshares",
    "The Creation of Avacyn",
    "Training Grounds",
    "Uncharted Haven",
    "Unclaimed Territory",
    "Urza's Incubator",
    "Utopia Sprawl",
    "Valgavoth's Lair",
    "Wheel of Misfortune",
    "Wishclaw Talisman"
]

TO_COUNTRY = "sweden"

LANGUAGE = "English"

# Check only the first product match by default
# Set to a higher number (e.g., 3) to check more versions if available
# This will increase scraping time.
MAX_PRODUCT_VERSIONS_TO_CHECK = 1


def calculate_shipping_price(filtered_df: pd.DataFrame, shipping_dict: dict, previous_node_path: list, current_node_index: int, current_value: float, value_increase: float):

    # This function calculates the shipping price, or increase in shipping price for a given seller/node. 
    # Since the shipping price increases with the value of the cards (at certain rates), we have the following scenarios:
    # - The current seller is already in the path, and the value of the cards does not reach the threshold for increased shipping.
    # - The current seller is already in the path, and the value of the cards does reach the threshold for increased shipping.
    # - The current seller is not in the path, meaning that the shipping price threshhold is the value increase of the cards.

    # We should first determine the country of the sellers so we can get the shipping price list for that country. 
    country = filtered_df.iloc[current_node_index]['country']
    shipping_price_list = shipping_dict[country.upper().replace(" ", "_")]

    # We should then calculate if the new value increases the shipping price, and by how much. 
    # We do this by iterating over the shipping price list and checking if the value increase is greater than the shipping price. Note that the list has the following format:
    # {
    #     "price": parsed_price,
    #     "maxValue": parsed_max_value,
    # } 
    previous_shipping_price = shipping_price_list[0]['price']
    new_shipping_price = previous_shipping_price
    for i, shipping_price in enumerate(shipping_price_list):
        if current_value > shipping_price['maxValue']:
            previous_shipping_price = shipping_price['price']
            new_shipping_price = shipping_price['price']
        elif current_value + value_increase > shipping_price['maxValue']:
            new_shipping_price = shipping_price['price']
        else:
            break
    shipping_price_increase = new_shipping_price - previous_shipping_price
    
    # Now we want to check if the new seller is in the path, and if so, we want to add the shipping price increase to the total shipping price.
    # Otherwise, we want to add the shipping price increase to the total shipping price.
    if current_node_index in previous_node_path:
        shipping_price = shipping_price_increase
    else:
        shipping_price = new_shipping_price
    
    
    return shipping_price

def find_cheapest_seller_group(filtered_df: pd.DataFrame, shipping_dict: dict, desired_cards_set: set):
    
    sorted_desired_cards_set = sorted(list(desired_cards_set))
    
    # For this algorithm, we first create an adjacency matrix of size | sellers | x | desired cards | 
    # where the value of edge[i][j] is the price of buying card j from seller i. Note that this does not include shipping costs.
    # We then use a greedy algorithm to find the minimum cost set of sellers that covers all desired cards.

    # Create adjacency matrix
    adjacency_matrix = np.zeros((len(filtered_df), len(sorted_desired_cards_set)))
    for i, row in filtered_df.iterrows():
        for j, card in enumerate(sorted_desired_cards_set):
            if pd.notna(row[card]):
                adjacency_matrix[i][j] = row[card]
            else:
                adjacency_matrix[i][j] = float('inf')
    
    # Now we want empty nodes the size of | sellers | x | desired cards |
    # where each node has the cheapest price, and the cheapest path to this node. 

    path_matrix = [[(float('inf'), []) for _ in range(len(sorted_desired_cards_set))] for _ in range(len(filtered_df))]

    # initiate first column of path matrix
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
    # We then iterate over all columns of the adjacency matrix and update the path matrix if the value is lower than the current value

    for j in tqdm.tqdm(range(1, len(sorted_desired_cards_set))):
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
    
    # Now we find the minimum cost path
    min_cost = float('inf')
    min_path = []
    for i in range(len(filtered_df)):
        if path_matrix[i][-1][0] < min_cost:
            min_cost = path_matrix[i][-1][0]
            min_path = path_matrix[i][-1][1]
    
    print(f"Minimum cost path: {min_path} with cost {min_cost}")
    print(f"Sellers in path: {[filtered_df.iloc[i]['seller'] for i in min_path]}") 

    # Should return a dictionary of seller names as keys, and a list of card names as values
    optimal_seller_groups = defaultdict(list)
    for i in range(len(min_path)):
        optimal_seller_groups[filtered_df.iloc[min_path[i]]['seller']].append(sorted_desired_cards_set[i])
    return optimal_seller_groups, min_cost


def filter_sellers_df(sellers_df, card_names):

    # This function will filter out sellers that sell the same cards as other sellers, keeping only the cheapest offer per card per seller. If two sellers offer multiple cards at different prices, it will keep the cheapest package deal. 

    # The input is a pandas dataframe with the following columns:
    # - seller
    # - country
    # - card_names, one column per card, the value will be the price of that card from the seller. If the seller does not offer a card, the value will be None. Remember that by using this system, we can save a lot of data from scraping, and then re-use it when finding the cheapest price for different combinations of cards. 
    # - link, the link to the listing.

    # The output is a pandas dataframe with the same columns, but with the sellers that sell the same cards as other sellers filtered out.

    
    output_df = pd.DataFrame(columns=sellers_df.columns)

    # First we extract all the combinations of cards that are being selled. 
    combinations = []

    for _, row in sellers_df.iterrows():
        cards_sold = [card for card in card_names if pd.notna(row[card])]
        cards_sold.sort()
        if cards_sold not in combinations:
            combinations.append(cards_sold)
    
    # for each combination, we now filter out all sellers that offer the same cards at a higher price and within the same country.
    for combination in combinations:
        if not combination: # Added check for empty combination
            continue
        other_cards = [card for card in card_names if card not in combination]
        cond_has_price_for_combination = sellers_df[combination].notna().all(axis=1)
        cond_is_null_for_others = sellers_df[other_cards].isna().all(axis=1)
        mask_exact_combination = cond_has_price_for_combination & cond_is_null_for_others
        sellers_with_exact_combination_df = sellers_df[mask_exact_combination]

        # Sort the dataframe rows based on price
        # This ensures we prioritize sellers with the lowest total price for the combination
        sellers_with_exact_combination_df = sellers_with_exact_combination_df.sort_values(by=combination, ascending=True)

        # Add only the cheapest seller for this combination to the output
        if not sellers_with_exact_combination_df.empty:
            temp_out_df = pd.DataFrame(columns=sellers_df.columns)
            for _, row in sellers_with_exact_combination_df.iterrows():
                # Check if we already have a seller from this country with the same combination
                # If so, compare the total price and keep the cheaper one
                country_mask = temp_out_df['country'] == row['country']
                if country_mask.any():
                    # Calculate total price for existing seller
                    existing_row = temp_out_df[country_mask].iloc[0]
                    existing_total = sum(existing_row[card] for card in combination if pd.notna(existing_row[card]))
                    
                    # Calculate total price for current seller
                    current_total = sum(row[card] for card in combination if pd.notna(row[card]))
                    
                    # If current seller is cheaper, replace the existing one
                    if current_total < existing_total:
                        temp_out_df = temp_out_df[~country_mask]
                        if temp_out_df.empty:
                            temp_out_df = pd.DataFrame([row])
                        else:
                            temp_out_df = pd.concat([temp_out_df, pd.DataFrame([row])], ignore_index=True)
                    else:
                        # Skip this row as we already have a cheaper seller from this country
                        continue
                else:
                    if temp_out_df.empty:
                        temp_out_df = pd.DataFrame([row])
                    else:
                        temp_out_df = pd.concat([temp_out_df, pd.DataFrame([row])], ignore_index=True)
            if not temp_out_df.empty:
                # Create a new DataFrame with the row and explicitly set dtypes to match sellers_df
                new_row_df = pd.DataFrame([row])
                # Ensure dtypes match by explicitly converting columns
                for col in sellers_df.columns:
                    if col in new_row_df.columns:
                        new_row_df[col] = new_row_df[col].astype(sellers_df[col].dtype)
                if output_df.empty:
                    output_df = new_row_df
                else:
                    output_df = pd.concat([output_df, new_row_df], ignore_index=True)
        else:
            print(f"No sellers found for combination {combination}")
    
    print(f"Found {len(output_df)} unique sellers after filtering.")
    return output_df

def create_sellers_dataframe(listings: pd.DataFrame, card_names: list[str]) -> tuple[pd.DataFrame, list[str]]:
    # Creates a dataframe from the listings dataframe containing the following columns:
    # - seller
    # - country
    # - card_names, one column per card, the value will be the price of that card from the seller. If the seller does not offer a card, the value will be None. Remember that by using this system, we can save a lot of data from scraping, and then re-use it when finding the cheapest price for different combinations of cards. 

    found_cards = {}
    for listing in listings.iterrows():
        card_name = str(listing[1]['card_name']).lower()
        if card_name not in card_names:
            continue
        found_cards[card_name] = True
    
    found_cards = list(found_cards.keys())
    print(f"Found {len(found_cards)} cards in the listings.")

    sellers_df = pd.DataFrame(columns=["seller", "country", "link", *found_cards])
    
    for listing in listings.iterrows():
        seller = listing[1]['seller']
        card_price = listing[1]['price']
        card_name = str(listing[1]['card_name']).lower()
        if card_name not in card_names:
            # We don't add cards that we are not looking for. 
            continue
        

        if seller in sellers_df['seller'].values:
            sellers_df.loc[sellers_df['seller'] == seller, card_name] = card_price
        else:
            row = {
                "seller": seller,
                "country": listing[1]['country'],
                **{card.lower(): None for card in found_cards}
            }
            row[card_name] = card_price
            if sellers_df.empty:
                sellers_df = pd.DataFrame([row])
            else:
                # Create a new DataFrame with the row and explicitly set dtypes to match sellers_df
                new_row_df = pd.DataFrame([row])
                # Ensure dtypes match by explicitly converting columns
                for col in sellers_df.columns:
                    if col in new_row_df.columns:
                        new_row_df[col] = new_row_df[col].astype(sellers_df[col].dtype)
                sellers_df = pd.concat([sellers_df, new_row_df], ignore_index=True)
    
    return sellers_df, found_cards


def parse_raw_data(raw_data: list[dict], previous_listings: pd.DataFrame = pd.DataFrame()) -> pd.DataFrame:
    # Parses the raw data from the CardApi and returns a dataframe with the following columns:
    # - seller
    # - card_name
    # - price
    # - country
    # - link
    # - Hash of the listing, so we can check if the listing is a duplicate before adding it to the dataframe.
    # The input data will be a list of dictionaries, where each dictionary contains the following values:
    # - seller
    # - card_name
    # - price
    # - country
    # - lin
    listings = None
    if not previous_listings.empty:
        listings = previous_listings
    else:
        listings = pd.DataFrame(columns=["seller", "card_name", "price", "country", "link", "hash"])
    
    for listing in raw_data:
        # Create a copy of the listing without the link for hashing
        listing_for_hash = {k: v for k, v in listing.items() if k != 'link'}
        # Convert the modified listing dictionary to a string for hashing
        listing_str = json.dumps(listing_for_hash, sort_keys=True)
        hash_value = hashlib.md5(listing_str.encode('utf-8')).hexdigest()
        row = {
            "seller": listing['seller'],
            "card_name": listing['card_name'],
            "price": listing['price'],
            "country": listing['country'],
            "link": listing['link'],
            "hash": hash_value
        }
        if hash_value in listings['hash'].values:
            continue
        # Create a new row with matching dtypes before concatenation
        new_row_df = pd.DataFrame([row])
        if not listings.empty:
            for col in listings.columns:
                if col in new_row_df.columns:
                    new_row_df[col] = new_row_df[col].astype(listings[col].dtype)
        
            listings = pd.concat([listings, new_row_df], ignore_index=True)
        else:
            listings = new_row_df
    print(f"listings count: {len(listings)}")
    return listings


def main():
    parser = argparse.ArgumentParser(description="Card Api and Analyzer")
    parser.add_argument(
        "--gather",
        action="store_true",
        help="Gather data for the cards and save the filtered results to ./listings_df.csv"
    )
    parser.add_argument(
        "--find-cheapest",
        action="store_true",
        help="The cheapest n number of options to calculate seller groups for. Default is 0, and will skip that step. "
    )
    parser.add_argument(
        "--shipping-dict-path",
        type=str,
        default=None,
        required=False,
        help="Path to CSV file to save data to and load data from. "
    )
    parser.add_argument("--listings-path",
        type=str,
        default=None,
        required=False,
        help="Path to CSV file to save data to and load unfiltered, raw data from. "
    )
    parser.add_argument(
        "--output",    
        type=str, 
        default=None,
        help="File to print analysis results to. "
    )
    args = parser.parse_args()

    card_names = [card.lower() for card in DESIRED_CARDS]
    card_names = list(set(card_names))
    gather_card_names = card_names.copy()
    
    listings_df = pd.DataFrame()
    raw_data = []

    if args.listings_path and os.path.exists(args.listings_path):
        print(f"--- Loading listings from: {args.listings_path} ---")
        listings_df = pd.read_csv(args.listings_path)
        # We also want to filter out card_names to only include the cards that are not in the listings_df
        gather_card_names = [card for card in DESIRED_CARDS if card not in listings_df['card_name'].values]

        
    if args.gather:
        # Gather more data
        api = CardApi()
        print("CardApi initialized.")
        raw_data = api.gather_data(gather_card_names)
        api.close()
    
        # Add new listings to the listings dataframe
        listings_df = parse_raw_data(raw_data, previous_listings=listings_df)

        # Save the listings dataframe to a csv file
        if args.listings_path:
            listings_df.to_csv(args.listings_path, index=False)
        else:
            listings_df.to_csv("listings_df.csv", index=False)
    
    
    if args.find_cheapest:
        # Create a sellers dataframe from the listings dataframe
        print(f"Creating sellers dataframe over {len(card_names)} cards from {len(listings_df)} listings")

        sellers_df, found_cards = create_sellers_dataframe(listings_df, card_names)

        print(f"Found {len(sellers_df)} unique sellers, and {len(found_cards)} cards in the listings.")

        # Since create_sellers_datafram will only add the cards we are looking for, we can filter out the cards that are not in the sellers_df.
        
        # Filter out sellers
        filtered_df = filter_sellers_df(sellers_df, found_cards)

        print(f"Filtered out to {len(filtered_df)} unique sellers.")
        
        # Load the shipping dictionary
        shipping_dict = None
        if args.shipping_dict_path:
            print(f"--- Loading shipping dictionary from: {args.shipping_dict_path} ---")
            if os.path.exists(args.shipping_dict_path):
                with open(args.shipping_dict_path, 'r') as f:
                    shipping_dict = json.load(f)
        if not shipping_dict:
            print(f"No shipping dictionary provided, scraping shipping prices for {TO_COUNTRY}")
            shipping_dict = ShippingApi.get_shipping_prices(TO_COUNTRY)
            
            if args.shipping_dict_path: 
                print(f"Saving shipping dictionary to {args.shipping_dict_path}")
                with open(args.shipping_dict_path, 'w') as f:
                    json.dump(shipping_dict, f)
            else:
                print(f"No shipping dictionary provided, saving to shipping_dict.json")
                with open("shipping_dict.json", 'w') as f:
                    json.dump(shipping_dict, f)
    
        
        # Find optimal seller groups based on cost
        desired_cards_as_set = set(found_cards)
        print(f"Finding optimal seller groups for {len(desired_cards_as_set)} cards")
        optimal_seller_groups, min_cost = find_cheapest_seller_group(filtered_df, shipping_dict, desired_cards_as_set)

        # Print results, prints where each card should be bought from
        print(f"--- Results ---")
        total_cost = 0
        
        output_file = None
        if args.output:
            output_file = open(args.output, "w")
        
        for seller, cards in optimal_seller_groups.items():
            for card in cards:
                # Use proper condition syntax with parentheses and check if link exists
                link_values = listings_df.loc[(listings_df['seller'] == seller) & (listings_df['card_name'] == card), 'link'].values
                link = link_values[0] if len(link_values) > 0 else None

                output_string = f"  - For {card}, the cheapest option is to buy from {seller} at {filtered_df.loc[filtered_df['seller'] == seller, card].values[0]}{f" (link: {link})" if link else ""}"
                print(output_string)
                if output_file:
                    output_file.write(output_string + "\n")
            total_cost += filtered_df.loc[filtered_df['seller'] == seller, cards].sum().sum()
        print(f"Total cost: {min_cost}, where {total_cost} is the sum of the prices of the cards.")
        if output_file:
            output_file.write(f"Total cost: {min_cost}\n")
            output_file.close()
    else:
        print("Find cheapest is zero, skipping data analysis part. ")
    
    
    
if __name__ == "__main__":
    main()