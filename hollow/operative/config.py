"""
Configuration — loads from .env automatically via python-dotenv.

Priority order (highest wins):
  1. Real environment variables already set in the shell / OS
  2. Values in your .env file
  3. Hardcoded defaults below

You never need to export anything or run `source .env`.
Just fill in .env and run:  uv run operative
"""

import os
from dotenv import load_dotenv

# Finds and loads .env from the directory you run operative from.
# override=False means real shell env vars always take precedence over .env.
load_dotenv(override=False)


class Config:
    # ── Instagram (Instaloader — FREE, no API key needed) ───────────────────
    IG_USERNAME: str = os.getenv("IG_USERNAME", "")
    IG_PASSWORD: str = os.getenv("IG_PASSWORD", "")

    # ── SerpAPI (Google search — 100 free searches/month) ───────────────────
    SERPAPI_KEY: str = os.getenv("SERPAPI_KEY", "")

    # ── Google Sheets ────────────────────────────────────────────────────────
    GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    SPREADSHEET_ID: str = os.getenv("SPREADSHEET_ID", "")
    SHEET_NAME: str = os.getenv("SHEET_NAME", "Gym Leads")

    # ── Scraper settings ─────────────────────────────────────────────────────
    REQUEST_DELAY_SECONDS: float = float(os.getenv("REQUEST_DELAY", "1.5"))
    TIMEOUT_SECONDS: int = int(os.getenv("TIMEOUT_SECONDS", "15"))
    SELENIUM_HEADLESS: bool = os.getenv("SELENIUM_HEADLESS", "true").lower() == "true"
