## DragonsLair card trade-in matcher

## Description

This includes an automatic scraper that will find all cards that are currently tradable in the DragonsLair shops, and match them with cards that you own, to tell you how much you can trade in your cards for (note that you trade in for other cards of that value). Useful if you want to trade some of your cards for other cards if you have, for example, a lot of duplicates.

## How it works

The scraper part will iterate through all cards in the DragonsLair single card website to gather all relevant card information for each card, and place this in a dataframe. Once the data has been gathered (takes about 1 hour and around 1000-5000 requests), it will match cards that you specify with these tradable cards to get the total value of cards you can trade in for. The owned cards support using exported cards from manabox, or any other .csv file that has the required properties (more on that in the Usage section). It currently only supports matching cards based on foil, set name and card name.

## Usage

To run the script, simply use

```
python main.py --owned-cards ./owned-cards.csv --output ./output.txt
```

Where `owned_cards.csv` is a `.csv` file that has `Name`, `Set Name`, `Foil`, and `Quantity`, and `output.txt` will be an output file containing the result. This commadn will gather tradable cards and save them to `./tradable_cards.csv`, so if you don't want to re-gather cards everything, use

```
python main.py --owned-cards ./owned-cards.csv --tradable-cards ./tradable_cards.csv --output ./output.txt
```

The program will then skip the gathering phase and instead use the cards found in `./tradable_cards.csv`.
