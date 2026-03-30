# Gym Lead Finder Agent

Finds **gyms, pilates studios, yoga centres, crossfit boxes, and fitness businesses** via Instagram + Google, scrapes their websites for contact info, and exports to **Google Sheets**.

**100% free to run.** Managed with [uv](https://github.com/astral-sh/uv).

---

## Quickstart

### 1. Install uv (if you don't have it)

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clone / unzip and set up the project

```bash
cd hollow

# Creates .venv and installs all dependencies from uv.lock — one command
uv sync
```

That's it. No `pip install`, no manual virtualenv, no version conflicts.

### 3. Configure credentials

```bash
cp .env.example .env
# Edit .env with your credentials (see below)
```

`.env`:
```env
IG_USERNAME=your_ig_username       # Instagram (secondary account recommended)
IG_PASSWORD=your_ig_password
SERPAPI_KEY=your_serpapi_key       # https://serpapi.com — 100 free/month
SPREADSHEET_ID=your_sheet_id      # from your Google Sheet URL
GOOGLE_CREDENTIALS_FILE=credentials.json
```

### 4. Set up Google Sheets (one time, ~5 minutes)

1. Go to https://console.cloud.google.com/
2. Enable **Google Sheets API** + **Google Drive API**
3. Create a **Service Account** → download JSON key → save as `credentials.json`
4. **Share your Google Sheet** with the service account email → give **Editor** access
5. Copy the Sheet ID from the URL:
   `https://docs.google.com/spreadsheets/d/`**`SHEET_ID_HERE`**`/edit`

### 5. Run

```bash
# Using the installed script
uv run operative

# With options
uv run operative --keywords gym pilates yoga crossfit --location "Mumbai" --max 100

# Or run main.py directly
uv run python main.py --location "Delhi"
```

---

## Commands reference

```bash
uv sync                        # Install / update all dependencies
uv add <package>               # Add a new dependency
uv remove <package>            # Remove a dependency
uv run operative               # Run the agent
uv run operative --help        # Show all CLI options
uv run ruff check .            # Lint the code
uv lock --upgrade              # Upgrade all packages to latest
```

---

## What it collects

| Field | Source |
|---|---|
| Business name | Instagram / Google |
| Instagram handle + URL | Instagram |
| Website URL | Instagram bio / Google |
| Email | Instagram business email, bio, website, /contact page |
| Phone | Instagram business phone, bio, website |
| Address | Website |
| Category | Instagram |
| Followers | Instagram |
| Facebook URL | Website |

---

## How it works

```
keywords + city
     │
     ├─► Instagram hashtag search (Instaloader, free)
     │      Searches: #gym, #gymlife, #gymbangalore, #pilatestudio …
     │      Fetches full profiles → business email/phone direct from Instagram API
     │
     ├─► Google search (SerpAPI, 100 free/month)
     │      Query: "gym Bangalore contact" etc.
     │
     ▼
  Scrape each website
     ├─► httpx (fast, no browser)
     └─► Selenium headless Chrome (fallback for JS / bot-protected sites)
         Scrapes homepage + /contact page
     │
     ▼
  Deduplicate by email / domain / Instagram handle
     │
     ▼
  Write to Google Sheets (skips existing rows on re-runs)
```

---

## Project structure

```
hollow/
├── pyproject.toml              # uv project config + dependencies
├── uv.lock                     # locked dependency tree (commit this)
├── .env.example                # copy to .env and fill in credentials
├── .gitignore
│
├── main.py                     # entry point — cli() + run_agent()
├── config.py                   # loads from .env / environment
│
├── scrapers/
│   ├── instagram_scraper.py    # Instaloader hashtag search + profile fetch
│   ├── google_search.py        # SerpAPI Google results
│   └── web_scraper.py          # httpx + Selenium contact extractor
│
├── utils/
│   ├── contact_extractor.py    # normalises raw data → lead dicts
│   └── deduplicator.py         # merges duplicates
│
└── output/
    └── sheets_writer.py        # pushes rows to Google Sheets
```

---

## Cost

| Tool | Free tier |
|---|---|
| Instaloader | Unlimited (free) |
| SerpAPI | 100 searches/month free |
| Google Sheets API | Free |
| Selenium + Chrome | Free |
| **Total** | **$0** |

---

## Tips

- Use a **secondary Instagram account** — Instaloader saves sessions locally so you only log in once
- Re-running the agent is safe — the Sheets writer skips rows already in the sheet
- Automate with cron:
  ```bash
  0 2 * * * cd /path/to/hollow && uv run operative --location "Bangalore" >> cron.log 2>&1
  ```
