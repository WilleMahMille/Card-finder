# Card finder

## GitHub Repository

🔗 **Repository**: [https://github.com/WilleMahMille/card-finder](https://github.com/WilleMahMille/card-finder)

This is a combined repository for various tools for finding, buying and trading cards in TCG:s (mainly based on Magic The Gathering, since that's what I'm currently into). Current features include finding which cards you own that can be traded in for other cards, finding the cheapest way to buy a set of cards (when taking shipping prices into consideration), as well as a manual browsing mode, where it automatically filters listings, gathers listings and saves these for later analysis.

## How to use

### Installations

This is built for python version 3.12.9, and might not work with other versions. Each subfolder includes a requirements.txt file that you can install using

```
pip install -r requirement.txt
```

For browser-functionality (currently in the CardMarket "api"), we need to install Playwrights dependencies using

```
playwright install
```

## Description of subfolders

### CardMarket

This includes a webscraper for automatically gathering listings from the CardMarket website. Worth noting that since CardMarket uses Cloudflare's anti-botting system, I wouldn't recommend using this too ofter or for too many cards (around 100 max), since it will be more and more strict with blocking access to the site if it notices bot-like behaviour. Otherwise, this scraper will scrape both shipping prices to a desired country, try to automatically gather filtered listings, and then use a dynamic programming approach to calculate the cheapest way of buying the desired cards on CardMarket.

### DragonsLair

This includes an automatic requestscraper that will find all cards that are currently tradable in the DragonsLair shops, and match them with cards that you own, to tell you how much you can trade in your cards for (note that you trade in for other cards of that value). Useful if you want to trade some of your cards for other cards if you have, for example, a lot of duplicates.
