"""
Website scraper — visits gym websites and extracts contact info.

Flow:
  1. Try httpx (fast, no browser overhead)
  2. If blocked (403/429) or JS-heavy → fall back to Selenium headless Chrome
  3. Scrape homepage + /contact page
  4. Extract: emails, phones, addresses, social links
"""

import re
import time
import asyncio
import logging
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# ── Regex patterns ──────────────────────────────────────────────────────────
EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE
)
PHONE_RE = re.compile(
    r"(?:\+?91[\s\-]?)?(?:\(?\d{3,5}\)?[\s\-]?)?\d{3,5}[\s\-]?\d{4,5}"
)
ADDRESS_RE = re.compile(
    r"\d+[,\s]+(?:[A-Za-z0-9\s]+(?:Street|St\.?|Road|Rd\.?|Avenue|Ave\.?|Lane|"
    r"Ln\.?|Nagar|Layout|Colony|Cross|Main|Block|Sector|Phase|Floor|Building|"
    r"Complex|Mall|Plaza)[,\s]+)+"
    r"(?:[A-Za-z\s]+,\s*)?(?:Bangalore|Bengaluru|Mumbai|Delhi|Chennai|"
    r"Hyderabad|Pune|Kolkata|Ahmedabad|[A-Z][a-z]{3,})\s*[-–]?\s*\d{6}",
    re.IGNORECASE,
)

CONTACT_PAGE_SLUGS = [
    "/contact", "/contact-us", "/contactus",
    "/about", "/about-us", "/reach-us",
    "/get-in-touch", "/info", "/location",
]

JUNK_EMAIL_DOMAINS = {
    "example.com", "yourdomain.com", "domain.com", "email.com",
    "test.com", "sentry.io", "w3.org", "schema.org", "wixpress.com",
    "squarespace.com", "wordpress.org",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


class WebScraper:
    def __init__(self, timeout: int = 15, delay: float = 1.5):
        self.timeout = timeout
        self.delay = delay

    async def scrape(self, url: str) -> dict:
        """Scrape a gym website. Returns extracted contact data."""
        if not url:
            return {}
        if not url.startswith("http"):
            url = "https://" + url
        url = url.rstrip("/")

        data = {"website": url}
        base_domain = urlparse(url).netloc

        emails, phones, addresses = set(), set(), set()
        socials = {}
        visited: set[str] = set()

        # Build pages to visit: homepage + contact page
        pages = [url]
        contact_url = self._guess_contact_url(url)
        if contact_url:
            pages.append(contact_url)

        for page_url in pages:
            if page_url in visited:
                continue
            visited.add(page_url)

            html = await self._fetch(page_url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")
            text = soup.get_text(separator=" ", strip=True)

            # mailto: and tel: links (most reliable)
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if href.startswith("mailto:"):
                    email = href[7:].split("?")[0].strip().lower()
                    if self._valid_email(email):
                        emails.add(email)
                elif href.startswith("tel:"):
                    phone = re.sub(r"[^\d+\-\s()]", "", href[4:]).strip()
                    if len(re.sub(r"\D", "", phone)) >= 7:
                        phones.add(phone)

            # Regex on page text
            for m in EMAIL_RE.findall(text):
                if self._valid_email(m.lower()):
                    emails.add(m.lower())

            for m in PHONE_RE.findall(text):
                digits = re.sub(r"\D", "", m)
                if 7 <= len(digits) <= 13:
                    phones.add(m.strip())

            for m in ADDRESS_RE.findall(text):
                addresses.add(m.strip())

            # Social links
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "instagram.com/" in href and not socials.get("instagram_url"):
                    socials["instagram_url"] = href.split("?")[0]
                elif "facebook.com/" in href and not socials.get("facebook_url"):
                    socials["facebook_url"] = href.split("?")[0]

            # Look for an in-page contact link if we haven't found it yet
            if len(pages) < 3:
                found = self._find_contact_link_in_page(soup, url, base_domain)
                if found and found not in visited:
                    pages.append(found)

            await asyncio.sleep(self.delay)

        if emails:
            data["email"] = "; ".join(sorted(emails)[:3])
        if phones:
            data["phone"] = "; ".join(sorted(phones, key=len)[:2])
        if addresses:
            data["address"] = sorted(addresses, key=len)[-1]  # longest = most complete

        data.update(socials)
        return data

    # ── Fetch helpers ────────────────────────────────────────────────────────

    async def _fetch(self, url: str) -> str | None:
        """Try httpx first; fall back to Selenium for blocked/JS sites."""
        html = await self._fetch_httpx(url)
        if html is None:
            log.info(f"    httpx failed for {url} — trying Selenium...")
            html = await asyncio.get_event_loop().run_in_executor(
                None, self._fetch_selenium, url
            )
        return html

    async def _fetch_httpx(self, url: str) -> str | None:
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    follow_redirects=True,
                    headers=HEADERS,
                ) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        return resp.text
                    elif resp.status_code in (403, 429, 503):
                        return None  # trigger Selenium fallback
                    else:
                        log.debug(f"    {url} → HTTP {resp.status_code}")
                        return None
            except (httpx.ConnectTimeout, httpx.ReadTimeout):
                await asyncio.sleep(1.5 * (attempt + 1))
            except Exception as e:
                log.debug(f"    httpx error {url}: {e}")
                return None
        return None

    def _fetch_selenium(self, url: str) -> str | None:
        """Selenium headless Chrome — handles JS-rendered pages and bot checks."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from webdriver_manager.chrome import ChromeDriverManager

            options = Options()
            options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1280,900")
            options.add_argument(f"user-agent={HEADERS['User-Agent']}")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)

            try:
                driver.set_page_load_timeout(self.timeout)
                driver.get(url)
                time.sleep(2.5)  # let JS render
                html = driver.page_source
                log.debug(f"    Selenium fetched {url} ({len(html)} chars)")
                return html
            finally:
                driver.quit()

        except ImportError:
            log.warning("Selenium / webdriver-manager not installed.")
            log.warning("Run: pip install selenium webdriver-manager")
            return None
        except Exception as e:
            log.error(f"    Selenium error for {url}: {e}")
            return None

    # ── URL helpers ──────────────────────────────────────────────────────────

    def _guess_contact_url(self, base_url: str) -> str | None:
        """Return the most likely contact page URL."""
        return urljoin(base_url, "/contact")

    def _find_contact_link_in_page(
        self, soup: BeautifulSoup, base_url: str, base_domain: str
    ) -> str | None:
        """Scan anchor tags for a contact/about link on the same domain."""
        for a in soup.find_all("a", href=True):
            href = a["href"].lower()
            text = (a.get_text() or "").lower().strip()
            if any(h in href or h in text for h in ["contact", "reach", "location", "about"]):
                full = urljoin(base_url, a["href"])
                if urlparse(full).netloc == base_domain:
                    return full
        return None

    # ── Validators ───────────────────────────────────────────────────────────

    def _valid_email(self, email: str) -> bool:
        if "@" not in email or len(email) > 80:
            return False
        domain = email.split("@")[-1]
        return (
            "." in domain
            and domain not in JUNK_EMAIL_DOMAINS
            and not any(email.endswith(ext) for ext in [".png", ".jpg", ".gif", ".svg"])
        )
