"""
Deduplicator — merges duplicate leads using email, website, and Instagram handle.
"""

import logging
from urllib.parse import urlparse

log = logging.getLogger(__name__)


def _normalize_domain(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url if url.startswith("http") else "https://" + url)
        domain = parsed.netloc.lower().lstrip("www.")
        return domain
    except Exception:
        return url.lower()


def _normalize_email(email: str) -> str:
    return (email or "").lower().strip()


def _normalize_handle(handle: str) -> str:
    return (handle or "").lower().strip().lstrip("@")


class Deduplicator:
    def deduplicate(self, leads: list[dict]) -> list[dict]:
        """
        Merge leads that share email, website domain, or Instagram handle.
        Later leads' non-empty fields overwrite earlier ones.
        """
        seen_email: dict[str, int] = {}
        seen_domain: dict[str, int] = {}
        seen_handle: dict[str, int] = {}
        merged: list[dict] = []

        for lead in leads:
            email = _normalize_email(lead.get("email", ""))
            domain = _normalize_domain(lead.get("website", ""))
            handle = _normalize_handle(lead.get("instagram_handle", ""))

            match_idx = None
            if email and email in seen_email:
                match_idx = seen_email[email]
            elif domain and domain in seen_domain:
                match_idx = seen_domain[domain]
            elif handle and handle in seen_handle:
                match_idx = seen_handle[handle]

            if match_idx is not None:
                # Merge: fill in missing fields from new lead
                existing = merged[match_idx]
                for key, val in lead.items():
                    if val and not existing.get(key):
                        existing[key] = val
                # Update source to "instagram+google" if both found
                if existing.get("source") != lead.get("source"):
                    existing["source"] = "instagram+google"
                log.debug(f"Merged duplicate: {lead.get('name', '')} → entry #{match_idx}")
            else:
                idx = len(merged)
                merged.append(dict(lead))
                if email:
                    seen_email[email] = idx
                if domain:
                    seen_domain[domain] = idx
                if handle:
                    seen_handle[handle] = idx

        log.info(f"Deduplication: {len(leads)} → {len(merged)} unique leads")
        return merged
