<div align="center">

# 📺 RoarZone TV — Auto-Updating M3U8 Playlist

**Live IPTV playlist scraped from [RoarZone TV](http://tv.roarzone.info/), hosted on Vercel with automatic 20-minute refresh.**

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/tahsinulmohsinbd/roarzone-tv-playlist)
&nbsp;&nbsp;
![Channels](https://img.shields.io/badge/channels-99-e50914?style=flat-square)
![Refresh](https://img.shields.io/badge/refresh-20%20min-22c55e?style=flat-square)
![Platform](https://img.shields.io/badge/hosted-Vercel-000?style=flat-square&logo=vercel)

</div>

---

## 🔗 Quick Access

**Playlist URL** — paste this into your IPTV player:

```
https://magnetic-omega.vercel.app/playlist.m3u8
```

**Landing Page** — [magnetic-omega.vercel.app](https://magnetic-omega.vercel.app)

> Works with **VLC**, **IPTV Smarters**, **TiviMate**, **OTT Navigator**, **Kodi**, and any M3U/M3U8-compatible player.

---

## 📋 Table of Contents

- [How It Works](#-how-it-works)
- [Channel Categories](#-channel-categories)
- [Project Structure](#-project-structure)
- [Architecture](#-architecture)
- [Deploy Your Own](#-deploy-your-own)
- [Local Development](#-local-development)
- [API Reference](#-api-reference)
- [Configuration](#-configuration)
- [Notes & Limitations](#-notes--limitations)
- [License](#-license)

---

## ⚙️ How It Works

```
User Request ──▶ Vercel CDN ──▶ Cache Hit?
                                   │
                          ┌────────┴────────┐
                          │ YES             │ NO
                          ▼                 ▼
                   Return cached     Python serverless
                   playlist          function runs
                                          │
                                    ┌─────┴─────┐
                                    ▼           ▼
                              Scrape main   Fetch stream
                              page for      URLs from
                              channels      player.php
                                    │           │
                                    └─────┬─────┘
                                          ▼
                                   Generate M3U8
                                   playlist
                                          │
                                          ▼
                                   Cache for 20min
                                   & return response
```

1. A **Vercel Python serverless function** at `/api/playlist` scrapes all channels from `tv.roarzone.info`
2. For each discovered channel, it hits `player.php?stream={channel}` to extract a **fresh tokenized m3u8 URL** from the HTML
3. All channels are assembled into a properly formatted **`#EXTM3U` playlist**
4. The response includes `Cache-Control: s-maxage=1200` — **Vercel's CDN caches it for 20 minutes**
5. After the cache expires, the next request automatically triggers a fresh scrape
6. **No cron jobs needed** — the CDN handles the refresh cycle entirely

---

## 🏷️ Channel Categories

| Category | Count | Examples |
|---|:---:|---|
| 🇧🇩 **Bangla** | 27 | BTV, NTV, Jamuna TV, Channel I, Maasranga, Star Jalsha, Zee Bangla |
| 🎭 **Entertainment** | 23 | Star Plus, Zee TV, Sony TV, Colors, Hum TV, Sony SAB |
| ⚽ **Sports** | 14 | T Sports, Star Sports 1/2, Sony Ten 1/2/3, Gazi TV, Euro Sports |
| 🎬 **Movies** | 10 | Star Movies, Sony Max, Zee Cinema, B4U Movies, Sony Pix |
| 📰 **News** | 8 | CNN, Al Jazeera, DW News, Somoy TV, Ekattor TV |
| 🌍 **Documentary** | 7 | Discovery HD, Nat Geo, Animal Planet, TLC, Sony BBC Earth |
| 👶 **Kids** | 6 | Cartoon Network, POGO, Disney Channel, Sony Yay |
| 🎵 **Music** | 4 | Gaan Bangla, B4U Music, Zing, 9XM |

**Total: 99 channels** across 8+ categories

---

## 📁 Project Structure

```
roarzone-tv-playlist/
│
├── api/
│   └── playlist.py          # Vercel serverless function (main scraper)
│
├── public/
│   └── index.html           # Landing page with copy-to-clipboard UI
│
├── scraper.py               # Standalone scraper for local use
├── playlist.m3u8            # Locally generated playlist (for reference)
│
├── vercel.json              # Vercel routing & build configuration
├── requirements.txt         # Python dependencies
├── .gitignore               # Git ignore rules
├── LICENSE                  # MIT License
└── README.md                # This file
```

---

## 🏗️ Architecture

### Serverless Function (`api/playlist.py`)

The core engine that runs on each request (or serves from CDN cache):

| Component | Description |
|---|---|
| **Channel Discovery** | Parses the main page HTML for `player.php?stream=` links, `data-stream` attributes, and `onclick` handlers |
| **Fallback List** | If scraping fails, uses a curated list of 80+ known channels |
| **Stream Fetcher** | Hits `player.php` for each channel, extracts tokenized m3u8 URLs via regex |
| **Parallel Execution** | Uses `ThreadPoolExecutor` with 10 workers for fast parallel fetching |
| **Playlist Generator** | Produces a properly formatted `#EXTM3U` file sorted by category |
| **CDN Caching** | Returns `s-maxage=1200, stale-while-revalidate=3600` headers |

### Standalone Scraper (`scraper.py`)

Full-featured CLI scraper with the same logic plus:
- Detailed logging with timestamps
- Category auto-detection from channel names
- Progress reporting and error summaries
- Writes `playlist.m3u8` to disk

---

## 🚀 Deploy Your Own

### Option 1: One-Click Deploy

Click the button below to fork and deploy instantly:

[![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https://github.com/tahsinulmohsinbd/roarzone-tv-playlist)

### Option 2: Vercel CLI

```bash
# Clone the repo
git clone https://github.com/tahsinulmohsinbd/roarzone-tv-playlist.git
cd roarzone-tv-playlist

# Install Vercel CLI
npm i -g vercel

# Login & deploy
vercel login
vercel --prod
```

### Option 3: Connect Git Repository

1. Push your fork to GitHub
2. Go to [vercel.com/new](https://vercel.com/new)
3. Import your repository
4. Vercel auto-detects the config and deploys

> After deployment, your playlist will be available at `https://<your-app>.vercel.app/playlist.m3u8`

---

## 🔧 Local Development

### Prerequisites

- Python 3.9+
- pip

### Setup

```bash
# Clone the repository
git clone https://github.com/tahsinulmohsinbd/roarzone-tv-playlist.git
cd roarzone-tv-playlist

# Install dependencies
pip install -r requirements.txt
```

### Run the Standalone Scraper

```bash
python scraper.py
```

This generates `playlist.m3u8` in the current directory with full logging output:

```
2026-03-15 13:12:48 [INFO] ============================================================
2026-03-15 13:12:48 [INFO] RoarZone TV M3U8 Playlist Scraper
2026-03-15 13:12:48 [INFO] ============================================================
2026-03-15 13:12:48 [INFO] Fetching main page to discover channels...
2026-03-15 13:12:49 [INFO] Found 99 stream links in HTML
2026-03-15 13:12:50 [INFO] Results: 99 succeeded, 0 failed
2026-03-15 13:12:50 [INFO] ✓ Playlist written to playlist.m3u8
```

### Test with Vercel Dev Server

```bash
vercel dev
# Opens at http://localhost:3000
# Playlist at http://localhost:3000/playlist.m3u8
```

---

## 📡 API Reference

### `GET /playlist.m3u8`

Returns the full M3U8 playlist with all channels.

| Header | Value |
|---|---|
| `Content-Type` | `application/x-mpegurl; charset=utf-8` |
| `Cache-Control` | `public, s-maxage=1200, stale-while-revalidate=3600` |
| `Access-Control-Allow-Origin` | `*` |

**Response Format:**
```
#EXTM3U
# RoarZone TV Playlist - Auto-generated
# Last updated: 2026-03-15 13:26:17 BDT
# Total channels: 99

#EXTINF:-1 group-title="Sports",T Sports
https://edge2.roarzone.info:8447/roarzone/edge2/tsports/index.m3u8?token=...

#EXTINF:-1 group-title="Bangla",Jamuna TV
https://edge2.roarzone.info:8447/roarzone/edge3/jamuna-tv/index.m3u8?token=...
```

### `GET /api/playlist`

Same as above — alternative endpoint.

### `GET /`

Landing page with playlist URL, stats, categories, and usage instructions.

---

## ⚙️ Configuration

Key constants in `api/playlist.py`:

| Variable | Default | Description |
|---|---|---|
| `BASE_URL` | `http://tv.roarzone.info` | Source website to scrape |
| `MAX_WORKERS` | `10` | Parallel threads for fetching streams |
| `REQUEST_TIMEOUT` | `15` seconds | HTTP request timeout |
| `MAX_RETRIES` | `2` | Retry attempts for failed requests |
| `CACHE_SECONDS` | `1200` (20 min) | CDN cache duration |

To change the refresh interval, modify `CACHE_SECONDS` in `api/playlist.py`.

---

## ⚠️ Notes & Limitations

| Item | Details |
|---|---|
| **BDIX Access** | Streams are served over Bangladesh's BDIX network. They work best from BDIX-connected ISPs. |
| **Token Expiry** | Stream tokens contain timestamps and expire. The 20-minute refresh keeps them valid. |
| **IP Binding** | Tokens may be bound to the server's IP. Playback works if your player can reach the stream servers. |
| **Vercel Limits** | Hobby plan: 100GB bandwidth/month, 10s function timeout. More than sufficient for this use case. |
| **Channel Availability** | Channels may go offline or change URLs. The scraper handles failures gracefully and skips unavailable channels. |

---

## 🛠️ Tech Stack

- **Runtime**: Python 3.12 on Vercel Serverless Functions
- **HTTP**: `requests` with session pooling
- **Parsing**: `BeautifulSoup4` + `lxml`
- **Concurrency**: `concurrent.futures.ThreadPoolExecutor`
- **Hosting**: Vercel (Edge CDN + Serverless)
- **Frontend**: Vanilla HTML/CSS/JS (landing page)

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

For personal and educational use only. Please respect RoarZone's terms of service.

---

<div align="center">

**Made with ❤️ for the IPTV community**

</div>
