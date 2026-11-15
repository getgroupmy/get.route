from bs4 import BeautifulSoup as BS
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import pandas as pd
import html
import re
import time
from datetime import datetime, timedelta

# A route total as Google Maps writes it in English: "35 min (12.3 km)",
# "3 hr 45 min (350 km)", "3 h 45 min (350 km)", "1 day 2 hr (1,900 km)",
# "4 min (900 m)". The lookbehind stops a road code fusing with the time
# ("E12 35 min" must not read as "1235 min").
DURATION_DISTANCE = re.compile(
    r'(?<![\w/])'
    r'(?:(\d+)\s*days?\s*)?'
    r'(?:(\d+)\s*(?:hrs?|h)\b\s*)?'
    r'(?:(\d+)\s*mins?\b\s*)?'
    r'\(\s*([\d.,]+)\s*(km|m)\s*\)'
)
# A number with a unit this parser does not know, right before a match
# ("3 Std. 45 min"): the match would drop that part, so it is refused.
UNREAD_UNIT_BEFORE = re.compile(r'(?<![\w.])\d+\s*[^\W\d_]{1,6}\.?\s*$')


def parse_route_total(panel_text):
    """(minutes, km) of the route total: the FIRST "time (distance)" in the
    directions panel (later ones are per-step). Raises ValueError rather than
    return a wrong number when the text is not fully understood."""
    for m in DURATION_DISTANCE.finditer(panel_text):
        days, hours, mins, dist, unit = m.groups()
        if not (days or hours or mins):
            continue                      # "(12 km)" with no time: not a total
        if UNREAD_UNIT_BEFORE.search(panel_text[:m.start()]):
            raise ValueError(f"unrecognised time unit before {m.group(0)!r}")
        if "," in dist and "." not in dist and re.search(r",\d{1,2}$", dist):
            raise ValueError(f"decimal comma in {m.group(0)!r}; load the page in English (hl=en)")
        km = float(dist.replace(",", ""))
        if unit == "m":
            km /= 1000
        return int(days or 0) * 1440 + int(hours or 0) * 60 + int(mins or 0), round(km, 3)
    raise ValueError("no route time/distance in the directions panel")


def with_english(url):
    """The URL with hl=en, so the page (and "Directions from") is in English.
    The rest of the URL is left exactly as copied."""
    base, sep, fragment = url.partition("#")
    path, _, query = base.partition("?")
    params = [p for p in query.split("&") if p and not p.startswith("hl=")]
    params.append("hl=en")
    return path + "?" + "&".join(params) + (sep + fragment if sep else "")


class TrafficScraper:
    def __init__(self, places, urls, headless=True):
        if not places or not urls:
            raise ValueError("Places and URLs must be provided.")
        if len(places) != len(urls):
            raise ValueError("The number of places and URLs must match.")
        
        self.places = places
        self.urls = urls
        self.data = {}
        
        chrome_options = Options()
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--ignore-ssl-errors')
        if headless:
            chrome_options.add_argument('--headless')
        # chrome_options.add_argument('--disable-gpu')
        self.chrome_options = chrome_options

    def scrape(self):
        traffic_data = {}
        for idx, url in enumerate(self.urls):
            driver = webdriver.Chrome(options=self.chrome_options)
            try:
                driver.get(with_english(url))
                # Wait (up to ~20s) for the directions panel instead of a fixed 3s
                for _ in range(20):
                    time.sleep(1)
                    page_source = driver.page_source
                    if "Directions from" in page_source:
                        time.sleep(1)
                        page_source = driver.page_source
                        break
            except Exception as e:
                raise ConnectionError(f"Failed to load page {url}: {str(e)}")
            finally:
                driver.quit()
            
            soup = BS(page_source, "html.parser")
            try:
                directions_text = re.search(r'"(Directions from.*?)"', str(soup)).group(1)
            except AttributeError:
                raise ValueError(f"Could not find directions text on page {url}")
            
            section = soup.find('div', attrs={'aria-label': html.unescape(directions_text)})
            if section is None:
                raise ValueError(f"Could not find traffic section for {self.places[idx]}")
            
            # Join span texts with a separator so adjacent text (e.g. road code
            # "E12" + "35 min") can't fuse into "E1235 min".
            panel_text = section.get_text(" ", strip=True)
            try:
                minutes, km = parse_route_total(panel_text)
            except ValueError as e:
                raise ValueError(f"Could not read route time/distance for {self.places[idx]}: {e}")
            traffic_data[self.places[idx]] = {"time": minutes, "distance": km}
        self.data = traffic_data
        return traffic_data

    def to_dataframe(self):
        if not self.data:
            raise ValueError("No data available. Please run scrape() first.")
        
        altered_data = {}
        for place, info in self.data.items():
            altered_data[place + " time"] = info["time"]
            altered_data[place + " distance"] = info["distance"]
        
        df = pd.DataFrame([altered_data])
        return df

    def to_csv(self, filename):
        df = self.to_dataframe()
        df.to_csv(filename, index=False)
        print(f"Data exported to {filename}")

    def start_scraping(self, duration_minutes=30, interval_minutes=5):
        """Repeatedly scrapes data for a certain duration at fixed intervals."""
        end_time = datetime.now() + timedelta(minutes=duration_minutes)
        all_dataframes = []

        while datetime.now() < end_time:
            print(f"Scraping at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.scrape()
            df = self.to_dataframe()
            df['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            all_dataframes.append(df)
            time.sleep(interval_minutes * 60)  # Sleep for 'interval_minutes' minutes

        final_df = pd.concat(all_dataframes, ignore_index=True)
        return final_df
