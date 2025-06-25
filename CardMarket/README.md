# Card market web scraper and price analysis

## Description

This includes a webscraper for automatically gathering listings from the CardMarket website. Worth noting that since CardMarket uses Cloudflare's anti-botting system, I wouldn't recommend using this too ofter or for too many cards (around 100 max), since it will be more and more strict with blocking access to the site if it notices bot-like behaviour. Otherwise, this scraper will scrape both shipping prices to a desired country, try to automatically gather filtered listings, and then use a dynamic programming approach to calculate the cheapest way of buying the desired cards on CardMarket.

## How it works

When running the scraper you will be presented with a menu on whether you want the gathering to be automatic, manual, save and exit or restart browser. You select the option you want by using a single keypress and then enter (the key is displayed after the option). If you input an incorrect key, the menu will be presented again until a correct option is chosen. In manual or automatic mode, the menu can be re-opened by pressing any key in the console again (somtimes a bit finicky-so press a couple of times and make sure to get an enter down). When a key is registered, it will tell you so, and send a stop-signal to the current mode, after which the menu will reappear when the previous mode has been successfully stopped.

### Automatic mode

Automatic gathering means that the program will browse for you and gather filtered listings. This mode will be detected by Cloudflare's anti-botting system, which after some time will present you with captcha's. No need to worry about this, as the program will automatically detect this, restart the browser and continue where it left off. After some more time, it wont even present a captcha, but instead just return an empty page. The program will once again automatically detect this, restart the browser, and continue where it left off. I haven't experimented further than this, but I believe the blocking-frequency becomes lower and lower, i.e. it blocks faster and faster, but using the program once in a while and for up to 100 cards should work just fine.

### Manual mode

Manual mode is where the program will let you browse cardmarket manually, and automatically scrape all listings on the pages you're visiting. Note that manual mode will also filter the listings based on country, type of seller and lowest quality (config file for this will be added when I have the time, for now it is described under Advanced Usage) This mode wont be detected by Cloudflare's anti-botting system, as it's a user browsing, but it's also considerably slower and more tedious to use. Nevertheless, if you have the patience and don't want to risk getting blocked from CardMarket, this is the way to go.

### Save and exit

This option will save all gathered listings and exit the gathering-phase. If you also specified that you want to find the cheapest buy-alternative, it will do so once all listings have been saved.

### Restart browser

If the browser somehow starts acting up, or you got blocked one too many times from using automatic mode, you can restart the browser to get a fresh client.

## Usage

The usage for this one is a bit complex, depending on how configured you want it to be, so I will split it up into basic usage and advanced usage.

### Basic Usage

All the command-line arguments can be listed using

```
python main.py -h
```

It it's the first time you use it, I recommend changing the `DESIRED_CARDS` in `main.py` to the cards you want (this will be done using .csv files when I have the time to add this funcitonality), `TO_COUNTRY` to the country you want to ship the cards to (make sure the country exists in either `market-api.py` or on the CardMarket website), and then run

```
python main.py --gather --find-cheapest --output ./output.txt
```

This will automatically gather the listings for the cards you want, save all listings to `./listings_df.csv`, gather shipping prices, save the shipping prices to `./shipping_dict.json`, calculate the cheapest way of buying the desired cards, and then write the result to `./output.txt`.

The second time you run it, you can include the previous listings and shipping dictionary. You can do this using

```
python main.py --gather --find-cheapest --shipping-dict-path ./shipping_dict.json --listings-path ./listings_df.csv --output ./output.txt
```

Note that `--gather` and `--find-cheapest` can be excluded if you only want to gather listings, or already have listings and want to find the cheapest way to buy certain cards.

### Advanced Usage

This part is if you want to configure filtering or how the shipping prices are fetched.

#### Filtering

The filtering on CardMarket is done through URL arguments, and is easily done in the scraper in the function `_modify_url`. To add, change or remove arguments, simply change this function. This function is called before a URL is loaded (i.e. a website is visited), meaning that you can create a whole flow of logic if you want very specific filtering based on your preferences.

#### Shipping prices

Here we have a few things that can be changed. First, if we want to buy a lot of expensive cards, we might want to up the `SHIPPING_MAX_VALUE`, which will make the scraper gather shipping prices up to that value (in euro). If you want to change how the shipping price is fetched, you can change the `ShippingApi` class, to fetch from places other than CardMarket, or if you have some other database that more accurately predicts shipping prices. Just note that the output format is a dictionary where the key is the country name, and the entry is a list sorted based on `maxValue` containing `price` for the shipping option and `maxValue` that determines the maximum value of the cards allowed to be shipped with this option (when buying from CardMarket, I think they automatically enforce this).
