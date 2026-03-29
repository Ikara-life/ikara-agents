"""
Google search scraper — uses SerpAPI to search for gym websites.
Docs: https://serpapi.com/search-api
Free tier: 100 searches/month
"""

import asyncio
import logging
import httpx

log = logging.getLogger(__name__)

SERPAPI_URL = "https://serpapi.com/search"


class GoogleSearchScraper:
    def __init__(self, serpapi_key: str):
        self.key = serpapi_key

    async def search(self, query: str, max_results: int = 20) -> list[dict]:
        """
        Search Google for gym-related results.
        Returns list of {title, link, snippet} dicts.
        """
        if self.key == "YOUR_SERPAPI_KEY_HERE":
            log.warning("SerpAPI key not set — skipping Google search.")
            return []

        results = []
        pages = max(1, min(max_results // 10, 3))  # up to 3 pages of results

        async with httpx.AsyncClient(timeout=30) as client:
            for page in range(pages):
                params = {
                    "q": query,
                    "api_key": self.key,
                    "engine": "google",
                    "num": 10,
                    "start": page * 10,
                    "gl": "in",   # country — change if needed
                    "hl": "en",
                }
                for attempt in range(3):
                    try:
                        resp = await client.get(SERPAPI_URL, params=params)
                        resp.raise_for_status()
                        data = resp.json()
                        organic = data.get("organic_results", [])
                        results.extend(organic)
                        log.info(f"  Google page {page+1}: {len(organic)} results")
                        break
                    except Exception as e:
                        log.error(f"SerpAPI attempt {attempt+1} failed: {e}")
                        await asyncio.sleep(2 ** attempt)

                await asyncio.sleep(1)  # be polite

        return results[:max_results]
