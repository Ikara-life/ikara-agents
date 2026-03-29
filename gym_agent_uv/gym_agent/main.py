"""
Gym Lead Finder Agent

CLI flags:
  --source      instagram | google | both   (default: both)
  --dry-run     print leads to log only, skip Google Sheets write
  --keywords    list of search terms
  --location    city / area
  --max         max Instagram profiles per keyword
"""

import asyncio
import argparse
import logging
from gym_agent.scrapers.instagram_scraper import InstagramScraper
from gym_agent.scrapers.web_scraper import WebScraper
from gym_agent.scrapers.google_search import GoogleSearchScraper
from gym_agent.utils.contact_extractor import ContactExtractor
from gym_agent.utils.deduplicator import Deduplicator
from gym_agent.output.sheets_writer import GoogleSheetsWriter
from gym_agent.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("agent.log"),
    ],
)
log = logging.getLogger(__name__)

# Fields printed per lead in dry-run / log-only mode
LOG_FIELDS = ["name", "instagram_handle", "email", "phone", "website", "address", "source"]


def _log_leads(leads: list[dict]) -> None:
    """Pretty-print leads to the log (used in --dry-run mode)."""
    log.info("=" * 60)
    log.info(f"DRY RUN — {len(leads)} leads found (not written to Sheets)")
    log.info("=" * 60)
    for i, lead in enumerate(leads, 1):
        log.info(f"  Lead {i:>3}:")
        for field in LOG_FIELDS:
            val = lead.get(field)
            if val:
                label = field.replace("_", " ").ljust(16)
                log.info(f"           {label}: {val}")
        log.info("  " + "-" * 40)


async def run_agent(
    keywords: list[str],
    location: str,
    max_results: int,
    source: str = "both",
    dry_run: bool = False,
) -> list[dict]:

    log.info(
        f"Gym Lead Finder | keywords={keywords} | location={location} "
        f"| source={source} | dry_run={dry_run}"
    )

    config   = Config()
    extractor = ContactExtractor()
    dedup    = Deduplicator()
    all_leads: list[dict] = []

    # ── Step 1: Instagram ────────────────────────────────────────────────────
    if source in ("instagram", "both"):
        log.info("=" * 60)
        log.info("STEP 1: Instagram scraping (Instaloader)")
        log.info("=" * 60)

        ig = InstagramScraper(
            ig_username=config.IG_USERNAME,
            ig_password=config.IG_PASSWORD,
        )

        for keyword in keywords:
            log.info(f"  Searching Instagram: '{keyword}' in '{location}'")
            profiles = ig.search(keyword, location=location, max_results=max_results)
            before = len(all_leads)
            for profile in profiles:
                lead = extractor.from_instagram_profile(profile)
                if lead:
                    all_leads.append(lead)
            log.info(
                f"  → {len(profiles)} profiles scraped, "
                f"{len(all_leads) - before} new leads extracted"
            )
    else:
        log.info("Skipping Instagram (--source=google)")

    # ── Step 2: Google search ────────────────────────────────────────────────
    if source in ("google", "both"):
        log.info("=" * 60)
        log.info("STEP 2: Google search (SerpAPI)")
        log.info("=" * 60)

        google = GoogleSearchScraper(serpapi_key=config.SERPAPI_KEY)

        for keyword in keywords:
            query = f"{keyword} {location} contact"
            log.info(f"  Searching Google: '{query}'")
            results = await google.search(query, max_results=20)
            before = len(all_leads)
            for r in results:
                lead = extractor.from_search_result(r)
                if lead:
                    all_leads.append(lead)
            log.info(
                f"  → {len(results)} results fetched, "
                f"{len(all_leads) - before} new leads extracted"
            )
    else:
        log.info("Skipping Google (--source=instagram)")

    # ── Step 3: Website scraping ─────────────────────────────────────────────
    log.info("=" * 60)
    log.info("STEP 3: Website scraping (httpx + Selenium fallback)")
    log.info("=" * 60)

    web = WebScraper(
        timeout=config.TIMEOUT_SECONDS,
        delay=config.REQUEST_DELAY_SECONDS,
    )

    sites_total = sum(1 for lead in all_leads if lead.get("website") and not lead.get("_scraped"))
    log.info(f"  {sites_total} websites to scrape")

    for i, lead in enumerate(all_leads):
        website = lead.get("website")
        if not website or lead.get("_scraped"):
            continue

        log.info(f"  [{i + 1}/{len(all_leads)}] {website}")
        scraped = await web.scrape(website)
        for key, val in scraped.items():
            if val and not lead.get(key):
                lead[key] = val
        lead["_scraped"] = True

    # ── Step 4: Deduplicate ───────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("STEP 4: Deduplication")
    log.info("=" * 60)

    unique = dedup.deduplicate(all_leads)
    log.info(f"  {len(all_leads)} raw → {len(unique)} unique leads")

    # ── Step 5: Output ────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("STEP 5: Output")
    log.info("=" * 60)

    if dry_run:
        _log_leads(unique)
    else:
        sheets = GoogleSheetsWriter(
            credentials_file=config.GOOGLE_CREDENTIALS_FILE,
            spreadsheet_id=config.SPREADSHEET_ID,
            sheet_name=config.SHEET_NAME,
        )
        sheets.write(unique)
        log.info(f"Done! View results at: {sheets.get_spreadsheet_url()}")

    return unique


def cli():
    """Entry point — registered as `gym-agent` in pyproject.toml."""
    parser = argparse.ArgumentParser(
        prog="gym-agent",
        description="Find gym / fitness leads from Instagram + Google → Google Sheets",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        default=["gym", "pilates", "yoga studio", "crossfit", "fitness studio"],
        metavar="KEYWORD",
        help="Search terms (default: gym pilates 'yoga studio' crossfit 'fitness studio')",
    )
    parser.add_argument(
        "--location",
        default="Bangalore",
        help="City / area to target (default: Bangalore)",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=50,
        metavar="N",
        help="Max Instagram profiles per keyword (default: 50)",
    )
    parser.add_argument(
        "--source",
        choices=["instagram", "google", "both"],
        default="both",
        help=(
            "Which sources to use:\n"
            "  instagram  — Instagram only (no SerpAPI key needed)\n"
            "  google     — Google search only\n"
            "  both       — Instagram + Google (default)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print found leads to the log only.\n"
            "Skips writing to Google Sheets — useful for testing."
        ),
    )

    args = parser.parse_args()
    asyncio.run(
        run_agent(
            keywords=args.keywords,
            location=args.location,
            max_results=args.max,
            source=args.source,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    cli()
