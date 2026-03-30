"""
ContactExtractor — normalizes raw data from Instagram profiles
and Google search results into a unified lead dict.
"""

import re
import logging

log = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"(?:\+?91[\s\-]?)?(?:\(?\d{3,5}\)?[\s\-]?)?\d{3,5}[\s\-]?\d{4,5}")
URL_RE = re.compile(r"https?://[^\s\"'>]+", re.IGNORECASE)

# Fitness-related keywords to qualify accounts
FITNESS_KEYWORDS = [
    "gym", "fitness", "pilates", "yoga", "crossfit", "zumba", "workout",
    "training", "coach", "trainer", "health", "wellness", "strength",
    "cardio", "aerobics", "bootcamp", "spinning", "cycle", "dance studio",
    "martial arts", "karate", "boxing", "mma", "physiotherapy", "physio"
]


class ContactExtractor:
    def from_instagram_profile(self, profile: dict) -> dict | None:
        """
        Parse an Apify Instagram profile scrape result.
        Expected keys: username, fullName, biography, externalUrl,
                       followersCount, businessEmail, businessPhone,
                       businessCategoryName, postsCount, profilePicUrl
        """
        if not profile:
            return None

        bio = (profile.get("biography") or "").lower()
        name = profile.get("fullName") or profile.get("username") or ""
        category = (profile.get("businessCategoryName") or "").lower()

        # Filter: only keep fitness-related accounts
        combined_text = f"{bio} {name.lower()} {category}"
        if not any(kw in combined_text for kw in FITNESS_KEYWORDS):
            log.debug(f"Skipping non-fitness account: @{profile.get('username')}")
            return None

        lead = {
            "source": "instagram",
            "name": name,
            "instagram_handle": "@" + profile.get("username", ""),
            "instagram_url": f"https://instagram.com/{profile.get('username', '')}",
            "bio": profile.get("biography", "")[:300],
            "category": profile.get("businessCategoryName", ""),
            "followers": profile.get("followersCount", ""),
            "website": self._clean_url(profile.get("externalUrl", "")),
            "email": self._extract_email_from_bio(profile),
            "phone": self._extract_phone_from_bio(profile),
        }

        return self._clean_lead(lead)

    def from_search_result(self, result: dict) -> dict | None:
        """
        Parse a SerpAPI organic result.
        Expected keys: title, link, snippet
        """
        if not result:
            return None

        title = result.get("title", "")
        snippet = result.get("snippet", "")
        url = result.get("link", "")

        combined = f"{title} {snippet}".lower()
        if not any(kw in combined for kw in FITNESS_KEYWORDS):
            return None

        lead = {
            "source": "google",
            "name": title,
            "website": self._clean_url(url),
            "bio": snippet[:300],
            "email": self._extract_email_from_text(snippet),
            "phone": self._extract_phone_from_text(snippet),
        }

        return self._clean_lead(lead)

    # ── Private helpers ─────────────────────────────────────────────────────

    def _extract_email_from_bio(self, profile: dict) -> str:
        # Business email (most reliable)
        biz_email = profile.get("businessEmail", "")
        if biz_email and "@" in biz_email:
            return biz_email.lower().strip()

        # Fallback: regex on bio
        bio = profile.get("biography", "")
        return self._extract_email_from_text(bio)

    def _extract_email_from_text(self, text: str) -> str:
        if not text:
            return ""
        matches = EMAIL_RE.findall(text)
        valid = [m.lower() for m in matches if self._valid_email(m)]
        return valid[0] if valid else ""

    def _extract_phone_from_bio(self, profile: dict) -> str:
        biz_phone = profile.get("businessPhoneNumber", "")
        if biz_phone:
            return biz_phone.strip()
        bio = profile.get("biography", "")
        return self._extract_phone_from_text(bio)

    def _extract_phone_from_text(self, text: str) -> str:
        if not text:
            return ""
        matches = PHONE_RE.findall(text)
        for m in matches:
            digits = re.sub(r"\D", "", m)
            if 7 <= len(digits) <= 13:
                return m.strip()
        return ""

    def _clean_url(self, url: str) -> str:
        if not url:
            return ""
        url = url.strip()
        if url and not url.startswith("http"):
            url = "https://" + url
        return url

    def _valid_email(self, email: str) -> bool:
        junk = {"example.com", "yourdomain.com", "sentry.io", "w3.org", "schema.org"}
        domain = email.split("@")[-1] if "@" in email else ""
        return domain not in junk and len(email) < 80

    def _clean_lead(self, lead: dict) -> dict:
        """Remove empty string values, keep None for missing."""
        return {k: (v if v != "" else None) for k, v in lead.items()}
