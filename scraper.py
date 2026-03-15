#!/usr/bin/env python3
"""
RoarZone TV M3U8 Playlist Scraper
==================================
Scrapes all available channels from http://tv.roarzone.info/
and generates a playlist.m3u8 file with fresh tokenized stream URLs.
"""

import re
import sys
import time
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── Configuration ──────────────────────────────────────────────────────────────
BASE_URL = "http://tv.roarzone.info"
PLAYER_URL = f"{BASE_URL}/player.php"
OUTPUT_FILE = "playlist.m3u8"
MAX_WORKERS = 10  # Parallel requests for fetching channel streams
REQUEST_TIMEOUT = 15  # seconds
MAX_RETRIES = 2

# ─── Logging Setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Session Setup ──────────────────────────────────────────────────────────────
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": BASE_URL,
})


def fetch_page(url, params=None):
    """Fetch a page with retries."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                log.warning(f"Retry {attempt + 1}/{MAX_RETRIES} for {url}: {e}")
                time.sleep(1)
            else:
                log.error(f"Failed to fetch {url}: {e}")
                return None


def discover_channels():
    """
    Discover all available channels from the main page.
    The main page loads channels via JavaScript. We parse the HTML/JS to extract
    channel slugs, names, categories, and logo URLs.
    """
    log.info("Fetching main page to discover channels...")
    html = fetch_page(BASE_URL)
    if not html:
        log.error("Could not fetch the main page. Trying alternative discovery...")
        return discover_channels_from_known_list()

    channels = []

    # Strategy 1: Look for JavaScript arrays/objects with channel data
    # Common patterns: channels = [...], channelList = [...], var data = [...]
    js_patterns = [
        r'(?:channels|channelList|channel_list|data)\s*[:=]\s*(\[.*?\]);',
        r'(?:channels|channelList|channel_list|data)\s*[:=]\s*(\{.*?\});',
    ]
    for pattern in js_patterns:
        matches = re.findall(pattern, html, re.DOTALL)
        for match in matches:
            log.info(f"Found JavaScript channel data")
            # Try to parse the JSON-like structure
            try:
                import json
                data = json.loads(match)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            ch = extract_channel_from_dict(item)
                            if ch:
                                channels.append(ch)
                elif isinstance(data, dict):
                    for key, item in data.items():
                        if isinstance(item, dict):
                            ch = extract_channel_from_dict(item)
                            if ch:
                                channels.append(ch)
            except (json.JSONDecodeError, Exception) as e:
                log.debug(f"JSON parse failed: {e}")

    # Strategy 2: Look for player.php links with stream parameters
    stream_links = re.findall(
        r'player\.php\?stream=([^\s"\'&]+)', html
    )
    if stream_links:
        log.info(f"Found {len(stream_links)} stream links in HTML")
        for slug in stream_links:
            slug = slug.strip()
            if slug and slug not in [ch.get("slug") for ch in channels]:
                name = slug.split("/")[-1] if "/" in slug else slug
                name = name.replace("-", " ").replace("_", " ").title()
                channels.append({
                    "slug": slug,
                    "name": name,
                    "category": guess_category(name),
                    "logo": "",
                })

    # Strategy 3: Look for onclick/href handlers with stream references
    soup = BeautifulSoup(html, "lxml")

    # Look for elements with data-stream, data-channel, or onclick attributes
    for el in soup.find_all(attrs={"data-stream": True}):
        slug = el.get("data-stream", "").strip()
        if slug:
            name = el.get_text(strip=True) or slug.split("/")[-1].replace("-", " ").title()
            if slug not in [ch.get("slug") for ch in channels]:
                channels.append({
                    "slug": slug,
                    "name": name,
                    "category": guess_category(name),
                    "logo": "",
                })

    for el in soup.find_all(attrs={"data-channel": True}):
        slug = el.get("data-channel", "").strip()
        if slug:
            name = el.get_text(strip=True) or slug.replace("-", " ").title()
            if slug not in [ch.get("slug") for ch in channels]:
                channels.append({
                    "slug": slug,
                    "name": name,
                    "category": guess_category(name),
                    "logo": "",
                })

    # Look for onclick handlers that reference streams
    for el in soup.find_all(onclick=True):
        onclick = el.get("onclick", "")
        stream_match = re.search(r"(?:stream|channel)\s*[=:]\s*['\"]([^'\"]+)['\"]", onclick)
        if stream_match:
            slug = stream_match.group(1).strip()
            name = el.get_text(strip=True) or slug.split("/")[-1].replace("-", " ").title()
            if slug not in [ch.get("slug") for ch in channels]:
                channels.append({
                    "slug": slug,
                    "name": name,
                    "category": guess_category(name),
                    "logo": "",
                })

    # Strategy 4: Look for channel images/logos that might indicate channel list
    for img in soup.find_all("img"):
        src = img.get("src", "")
        alt = img.get("alt", "")
        if "tvassets" in src or "channel" in src.lower():
            # Try to find parent link or data attribute
            parent = img.find_parent("a")
            if parent:
                href = parent.get("href", "")
                stream_match = re.search(r"stream=([^\s&]+)", href)
                if stream_match:
                    slug = stream_match.group(1).strip()
                    name = alt or slug.split("/")[-1].replace("-", " ").title()
                    if slug not in [ch.get("slug") for ch in channels]:
                        channels.append({
                            "slug": slug,
                            "name": name,
                            "category": guess_category(name),
                            "logo": src,
                        })

    # If no channels found from main page, fall back to known list
    if not channels:
        log.warning("No channels discovered from main page. Using known channel list...")
        channels = discover_channels_from_known_list()

    # Deduplicate by slug
    seen = set()
    unique = []
    for ch in channels:
        if ch["slug"] not in seen:
            seen.add(ch["slug"])
            unique.append(ch)
    
    log.info(f"Total unique channels discovered: {len(unique)}")
    return unique


def extract_channel_from_dict(item):
    """Extract channel info from a dictionary."""
    slug = (
        item.get("stream")
        or item.get("slug")
        or item.get("url")
        or item.get("channel")
        or item.get("id")
    )
    if not slug:
        return None
    name = (
        item.get("name")
        or item.get("title")
        or item.get("channel_name")
        or slug.split("/")[-1].replace("-", " ").title()
    )
    category = (
        item.get("category")
        or item.get("group")
        or item.get("group_title")
        or item.get("type")
        or guess_category(name)
    )
    logo = (
        item.get("logo")
        or item.get("image")
        or item.get("icon")
        or item.get("tvg_logo")
        or ""
    )
    return {"slug": str(slug), "name": str(name), "category": str(category), "logo": str(logo)}


def guess_category(name):
    """Guess channel category from its name."""
    name_lower = name.lower()
    sports_keywords = [
        "sport", "cricket", "t sport", "tsport", "gazi", "willow",
        "sky sport", "star sport", "sony ten", "sony six", "espn", "ptv sport",
    ]
    kids_keywords = ["cartoon", "nick", "disney", "pogo", "sonic", "animax", "cbeebies", "kids", "yay"]
    news_keywords = ["news", "al jazeera", "cnn", "bbc world", "dw ", "somoy", "ekattor"]
    music_keywords = ["music", "gaan", "sangeet", "mtv", "9xm", "9xo", "zing", "zoom", "dhoom"]
    movie_keywords = ["movie", "cinema", "hbo", "pix", "max", "flix", "talkies", "b4u"]
    doc_keywords = ["discovery", "natgeo", "nat geo", "animal", "science", "tlc"]
    islamic_keywords = ["makkah", "madina", "islamic", "al dawah", "quran"]
    bangla_keywords = [
        "bangla", "btv", "ntv", "rtv", "channel i", "channel 9", "channel 24",
        "jamuna", "independent", "deepto", "maasranga", "desh tv", "asian tv",
        "boishakhi", "ekushy", "mohona", "sa tv", "nagorik", "bijoy",
        "ekhon", "duronto", "dbc", "atn", "star jalsha", "zee bangla",
        "colors bangla", "ruposhi",
    ]

    for kw in sports_keywords:
        if kw in name_lower:
            return "Sports"
    for kw in kids_keywords:
        if kw in name_lower:
            return "Kids"
    for kw in news_keywords:
        if kw in name_lower:
            return "News"
    for kw in music_keywords:
        if kw in name_lower:
            return "Music"
    for kw in movie_keywords:
        if kw in name_lower:
            return "Movies"
    for kw in doc_keywords:
        if kw in name_lower:
            return "Documentary"
    for kw in islamic_keywords:
        if kw in name_lower:
            return "Religious"
    for kw in bangla_keywords:
        if kw in name_lower:
            return "Bangla"

    return "Entertainment"


def discover_channels_from_known_list():
    """
    Fallback: Use a known list of RoarZone channels with their stream slugs.
    This list is based on research of the RoarZone TV service.
    """
    log.info("Using known channel list as fallback...")

    known_channels = [
        # ─── Sports ──────────────────────────────────────────────────────────
        {"slug": "edge2/tsports", "name": "T Sports", "category": "Sports", "logo": ""},
        {"slug": "edge2/starsports1", "name": "Star Sports 1", "category": "Sports", "logo": ""},
        {"slug": "edge2/starsports2", "name": "Star Sports 2", "category": "Sports", "logo": ""},
        {"slug": "edge2/starsports1hd", "name": "Star Sports 1 HD", "category": "Sports", "logo": ""},
        {"slug": "edge2/starsportsselect1", "name": "Star Sports Select 1", "category": "Sports", "logo": ""},
        {"slug": "edge2/starsportsselect2", "name": "Star Sports Select 2", "category": "Sports", "logo": ""},
        {"slug": "edge2/sonyten1", "name": "Sony Ten 1", "category": "Sports", "logo": ""},
        {"slug": "edge2/sonyten2", "name": "Sony Ten 2", "category": "Sports", "logo": ""},
        {"slug": "edge2/sonyten3", "name": "Sony Ten 3", "category": "Sports", "logo": ""},
        {"slug": "edge2/sonysix", "name": "Sony Six", "category": "Sports", "logo": ""},
        {"slug": "edge2/sonyespn", "name": "Sony ESPN", "category": "Sports", "logo": ""},
        {"slug": "edge2/gazitv", "name": "Gazi TV", "category": "Sports", "logo": ""},
        {"slug": "edge2/willow", "name": "Willow Cricket", "category": "Sports", "logo": ""},
        {"slug": "edge2/skysportscricket", "name": "Sky Sports Cricket", "category": "Sports", "logo": ""},
        {"slug": "edge2/skysportsmix", "name": "Sky Sports Mix", "category": "Sports", "logo": ""},
        {"slug": "edge2/ptvsports", "name": "PTV Sports", "category": "Sports", "logo": ""},

        # ─── Bangla ──────────────────────────────────────────────────────────
        {"slug": "edge2/btv", "name": "BTV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/btvworld", "name": "BTV World", "category": "Bangla", "logo": ""},
        {"slug": "edge2/ntv", "name": "NTV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/rtv", "name": "RTV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/atnbangla", "name": "ATN Bangla", "category": "Bangla", "logo": ""},
        {"slug": "edge2/atnnews", "name": "ATN News", "category": "Bangla", "logo": ""},
        {"slug": "edge2/channel9", "name": "Channel 9", "category": "Bangla", "logo": ""},
        {"slug": "edge2/channel24", "name": "Channel 24", "category": "Bangla", "logo": ""},
        {"slug": "edge2/channeli", "name": "Channel I", "category": "Bangla", "logo": ""},
        {"slug": "edge2/jamunatv", "name": "Jamuna TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/independenttv", "name": "Independent TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/maasranga", "name": "Maasranga", "category": "Bangla", "logo": ""},
        {"slug": "edge2/somoytv", "name": "Somoy TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/ekhon", "name": "Ekhon TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/deshtv", "name": "Desh TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/deepto", "name": "Deepto TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/dbcnews", "name": "DBC News", "category": "Bangla", "logo": ""},
        {"slug": "edge2/ekattortv", "name": "Ekattor TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/banglavision", "name": "Banglavision TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/asiantv", "name": "Asian TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/boishakhitv", "name": "Boishakhi TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/satv", "name": "SA TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/nagoriktv", "name": "Nagorik TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/mohonatv", "name": "Mohona TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/mytv", "name": "MY TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/ekushytv", "name": "Ekushy TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/news24", "name": "News 24", "category": "Bangla", "logo": ""},
        {"slug": "edge2/durontotv", "name": "Duronto TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/sangsadtv", "name": "Sangsad TV", "category": "Bangla", "logo": ""},
        {"slug": "edge2/bijoytv", "name": "Bijoy TV", "category": "Bangla", "logo": ""},

        # ─── Bangla Entertainment ────────────────────────────────────────────
        {"slug": "edge2/starjalsha", "name": "Star Jalsha", "category": "Bangla Entertainment", "logo": ""},
        {"slug": "edge2/zeebangla", "name": "Zee Bangla", "category": "Bangla Entertainment", "logo": ""},
        {"slug": "edge2/colorsbangla", "name": "Colors Bangla", "category": "Bangla Entertainment", "logo": ""},
        {"slug": "edge2/starjalshamovies", "name": "Star Jalsha Movies", "category": "Bangla Entertainment", "logo": ""},
        {"slug": "edge2/zeebanglacinema", "name": "Zee Bangla Cinema", "category": "Bangla Entertainment", "logo": ""},
        {"slug": "edge2/ruposhibangla", "name": "Ruposhi Bangla", "category": "Bangla Entertainment", "logo": ""},
        {"slug": "edge2/sangeetbangla", "name": "Sangeet Bangla", "category": "Bangla Entertainment", "logo": ""},
        {"slug": "edge2/akaashaath", "name": "Akaash Aath", "category": "Bangla Entertainment", "logo": ""},
        {"slug": "edge2/sonyaath", "name": "Sony Aath", "category": "Bangla Entertainment", "logo": ""},

        # ─── Hindi Entertainment ─────────────────────────────────────────────
        {"slug": "edge2/starplus", "name": "Star Plus", "category": "Hindi Entertainment", "logo": ""},
        {"slug": "edge2/zeetv", "name": "Zee TV", "category": "Hindi Entertainment", "logo": ""},
        {"slug": "edge2/sonytv", "name": "Sony TV", "category": "Hindi Entertainment", "logo": ""},
        {"slug": "edge2/sonysab", "name": "Sony SAB", "category": "Hindi Entertainment", "logo": ""},
        {"slug": "edge2/colors", "name": "Colors TV", "category": "Hindi Entertainment", "logo": ""},
        {"slug": "edge2/andtv", "name": "And TV", "category": "Hindi Entertainment", "logo": ""},
        {"slug": "edge2/starbharat", "name": "Star Bharat", "category": "Hindi Entertainment", "logo": ""},
        {"slug": "edge2/starworld", "name": "Star World", "category": "Hindi Entertainment", "logo": ""},
        {"slug": "edge2/zeeanmol", "name": "Zee Anmol", "category": "Hindi Entertainment", "logo": ""},

        # ─── Movies ──────────────────────────────────────────────────────────
        {"slug": "edge2/hbo", "name": "HBO", "category": "Movies", "logo": ""},
        {"slug": "edge2/starmovies", "name": "Star Movies", "category": "Movies", "logo": ""},
        {"slug": "edge2/sonymax", "name": "Sony Max", "category": "Movies", "logo": ""},
        {"slug": "edge2/sonypix", "name": "Sony Pix", "category": "Movies", "logo": ""},
        {"slug": "edge2/zeecinema", "name": "Zee Cinema", "category": "Movies", "logo": ""},
        {"slug": "edge2/stargold", "name": "Star Gold", "category": "Movies", "logo": ""},
        {"slug": "edge2/moviesnow", "name": "Movies Now", "category": "Movies", "logo": ""},
        {"slug": "edge2/andflix", "name": "And Flix", "category": "Movies", "logo": ""},
        {"slug": "edge2/andpictures", "name": "And Pictures", "category": "Movies", "logo": ""},
        {"slug": "edge2/zeecafe", "name": "Zee Cafe HD", "category": "Movies", "logo": ""},
        {"slug": "edge2/b4umovies", "name": "B4U Movies", "category": "Movies", "logo": ""},
        {"slug": "edge2/zeebollywood", "name": "Zee Bollywood", "category": "Movies", "logo": ""},
        {"slug": "edge2/zeeaction", "name": "Zee Action", "category": "Movies", "logo": ""},
        {"slug": "edge2/banglatalkies", "name": "Bangla Talkies", "category": "Movies", "logo": ""},
        {"slug": "edge2/movieplus", "name": "Movie Plus", "category": "Movies", "logo": ""},
        {"slug": "edge2/moviebanglatv", "name": "Movie Bangla TV", "category": "Movies", "logo": ""},
        {"slug": "edge2/mnx", "name": "MNX", "category": "Movies", "logo": ""},
        {"slug": "edge2/lotusmacau", "name": "Lotus Macau", "category": "Movies", "logo": ""},
        {"slug": "edge2/colorsinfinty", "name": "Colors Infinity", "category": "Movies", "logo": ""},
        {"slug": "edge2/comedycentral", "name": "Comedy Central", "category": "Movies", "logo": ""},

        # ─── Kids ────────────────────────────────────────────────────────────
        {"slug": "edge2/cartoonnetwork", "name": "Cartoon Network", "category": "Kids", "logo": ""},
        {"slug": "edge2/nickelodeon", "name": "Nickelodeon", "category": "Kids", "logo": ""},
        {"slug": "edge2/pogo", "name": "POGO", "category": "Kids", "logo": ""},
        {"slug": "edge2/sonic", "name": "Sonic", "category": "Kids", "logo": ""},
        {"slug": "edge2/disneychannel", "name": "Disney Channel", "category": "Kids", "logo": ""},
        {"slug": "edge2/disneyxd", "name": "Disney XD", "category": "Kids", "logo": ""},
        {"slug": "edge2/nickbangla", "name": "Nick Bangla", "category": "Kids", "logo": ""},
        {"slug": "edge2/nickjr", "name": "Nick Junior", "category": "Kids", "logo": ""},
        {"slug": "edge2/bbccbeebies", "name": "BBC CBeebies", "category": "Kids", "logo": ""},
        {"slug": "edge2/discoverykids", "name": "Discovery Kids", "category": "Kids", "logo": ""},
        {"slug": "edge2/sonyyay", "name": "Sony Yay", "category": "Kids", "logo": ""},

        # ─── Documentary ─────────────────────────────────────────────────────
        {"slug": "edge2/discovery", "name": "Discovery Channel", "category": "Documentary", "logo": ""},
        {"slug": "edge2/discoveryhd", "name": "Discovery HD", "category": "Documentary", "logo": ""},
        {"slug": "edge2/natgeo", "name": "National Geographic", "category": "Documentary", "logo": ""},
        {"slug": "edge2/natgeowild", "name": "Nat Geo Wild", "category": "Documentary", "logo": ""},
        {"slug": "edge2/natgeopeople", "name": "Nat Geo People", "category": "Documentary", "logo": ""},
        {"slug": "edge2/animalplanet", "name": "Animal Planet", "category": "Documentary", "logo": ""},
        {"slug": "edge2/sonybbcearth", "name": "Sony BBC Earth", "category": "Documentary", "logo": ""},

        # ─── Music ───────────────────────────────────────────────────────────
        {"slug": "edge2/gaanbangla", "name": "Gaan Bangla", "category": "Music", "logo": ""},
        {"slug": "edge2/dhoommusic", "name": "Dhoom Music", "category": "Music", "logo": ""},
        {"slug": "edge2/atnmusic", "name": "ATN Music", "category": "Music", "logo": ""},
        {"slug": "edge2/sonymix", "name": "Sony Mix", "category": "Music", "logo": ""},
        {"slug": "edge2/9xm", "name": "9XM", "category": "Music", "logo": ""},
        {"slug": "edge2/b4umusic", "name": "B4U Music", "category": "Music", "logo": ""},
        {"slug": "edge2/zing", "name": "Zing", "category": "Music", "logo": ""},
        {"slug": "edge2/zoom", "name": "Zoom", "category": "Music", "logo": ""},
        {"slug": "edge2/mtvbeats", "name": "MTV Beats", "category": "Music", "logo": ""},

        # ─── News ────────────────────────────────────────────────────────────
        {"slug": "edge2/aljazeera", "name": "Al Jazeera", "category": "News", "logo": ""},
        {"slug": "edge2/dwnews", "name": "DW News", "category": "News", "logo": ""},

        # ─── Religious ───────────────────────────────────────────────────────
        {"slug": "edge2/makkahlive", "name": "Makkah Live", "category": "Religious", "logo": ""},
        {"slug": "edge2/aldawah", "name": "Al Dawah", "category": "Religious", "logo": ""},

        # ─── Pakistani ───────────────────────────────────────────────────────
        {"slug": "edge2/humtv", "name": "Hum TV", "category": "Pakistani", "logo": ""},
        {"slug": "edge2/hummasala", "name": "Hum Masala", "category": "Pakistani", "logo": ""},
        {"slug": "edge2/humsitaray", "name": "Hum Sitaray", "category": "Pakistani", "logo": ""},
        {"slug": "edge2/ptvworld", "name": "PTV World", "category": "Pakistani", "logo": ""},
    ]

    return known_channels


def fetch_stream_url(channel):
    """
    Fetch the tokenized m3u8 stream URL for a single channel
    by hitting the player.php page and extracting the URL from HTML source.
    """
    slug = channel["slug"]
    log.debug(f"Fetching stream URL for: {channel['name']} ({slug})")

    html = fetch_page(PLAYER_URL, params={"stream": slug})
    if not html:
        return None

    # Extract the m3u8 URL from the page source
    # Pattern: source src="...index.m3u8?token=..." or hls.loadSource('...')
    m3u8_patterns = [
        r'(?:src|source)\s*=\s*["\']([^"\']*\.m3u8[^"\']*)["\']',
        r'loadSource\s*\(\s*["\']([^"\']*\.m3u8[^"\']*)["\']',
        r'["\']([^"\']*\.m3u8\?token=[^"\']*)["\']',
        r'(https?://[^\s"\'<>]*\.m3u8[^\s"\'<>]*)',
    ]

    for pattern in m3u8_patterns:
        matches = re.findall(pattern, html)
        if matches:
            # Take the first unique URL (deduplicate)
            url = matches[0].strip()
            if url and "m3u8" in url:
                log.debug(f"  ✓ Found stream: {channel['name']}")
                return url

    log.warning(f"  ✗ No stream URL found for: {channel['name']}")
    return None


def generate_playlist(channels_with_urls):
    """Generate the M3U8 playlist file."""
    bdt = timezone(timedelta(hours=6))
    now = datetime.now(bdt).strftime("%Y-%m-%d %H:%M:%S BDT")

    lines = [
        "#EXTM3U",
        f"# RoarZone TV Playlist - Auto-generated",
        f"# Last updated: {now}",
        f"# Total channels: {len(channels_with_urls)}",
        f"# Source: {BASE_URL}",
        "",
    ]

    # Sort by category then name
    channels_with_urls.sort(key=lambda c: (c["category"], c["name"]))

    current_category = None
    for ch in channels_with_urls:
        if ch["category"] != current_category:
            current_category = ch["category"]
            lines.append(f"# ═══ {current_category.upper()} ═══")

        # Build EXTINF line
        extinf_parts = [f'#EXTINF:-1']
        if ch.get("logo"):
            extinf_parts.append(f'tvg-logo="{ch["logo"]}"')
        extinf_parts.append(f'group-title="{ch["category"]}"')
        extinf_line = " ".join(extinf_parts) + f',{ch["name"]}'

        lines.append(extinf_line)
        lines.append(ch["url"])

    return "\n".join(lines) + "\n"


def main():
    log.info("=" * 60)
    log.info("RoarZone TV M3U8 Playlist Scraper")
    log.info("=" * 60)

    # Step 1: Discover channels
    channels = discover_channels()
    if not channels:
        log.error("No channels discovered. Exiting.")
        sys.exit(1)

    log.info(f"\nDiscovered {len(channels)} channels. Fetching stream URLs...\n")

    # Step 2: Fetch stream URLs in parallel
    channels_with_urls = []
    failed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_channel = {
            executor.submit(fetch_stream_url, ch): ch
            for ch in channels
        }

        for future in as_completed(future_to_channel):
            ch = future_to_channel[future]
            try:
                url = future.result()
                if url:
                    ch["url"] = url
                    channels_with_urls.append(ch)
                else:
                    failed += 1
            except Exception as e:
                log.error(f"Error fetching {ch['name']}: {e}")
                failed += 1

    log.info(f"\n{'=' * 60}")
    log.info(f"Results: {len(channels_with_urls)} succeeded, {failed} failed")
    log.info(f"{'=' * 60}\n")

    if not channels_with_urls:
        log.error("No channels with valid stream URLs. Exiting.")
        sys.exit(1)

    # Step 3: Generate playlist
    playlist_content = generate_playlist(channels_with_urls)

    # Step 4: Write to file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(playlist_content)

    log.info(f"✓ Playlist written to {OUTPUT_FILE}")
    log.info(f"  Channels: {len(channels_with_urls)}")

    # Print categories summary
    categories = {}
    for ch in channels_with_urls:
        cat = ch["category"]
        categories[cat] = categories.get(cat, 0) + 1
    log.info("\nChannels by category:")
    for cat, count in sorted(categories.items()):
        log.info(f"  {cat}: {count}")


if __name__ == "__main__":
    main()
