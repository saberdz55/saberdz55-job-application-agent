"""Internshala platform integration."""

import json
import os
import re

from playwright.async_api import Page

from src.platforms.base import BasePlatform
from src.platforms.internshala.scraper import scrape_jobs
from src.platforms.internshala.applier import apply_to_job
from src.browser.manager import BrowserManager
from src.utils.config import INTERNSHALA_STATE_PATH, encrypt
from src.utils.logger import get_logger

logger = get_logger("internshala")
BASE = "https://internshala.com"

DOMAIN_SLUG_MAP = {
    "software development": "software-development",
    "software developer": "software-development",
    "software engineering": "software-development",
    "data science": "data-science",
    "data scientist": "data-science",
    "artificial intelligence": "artificial-intelligence",
    "ai": "artificial-intelligence",
    "machine learning": "machine-learning",
    "cloud computing": "cloud-computing",
    "cyber security": "cyber-security",
    "information technology": "information-technology",
    "engineering": "engineering",
    "design": "design",
    "digital marketing": "digital-marketing",
    "marketing": "marketing",
    "sales": "sales",
    "finance": "finance",
    "human resources": "human-resources",
    "hr": "human-resources",
    "operations": "operations",
    "product management": "product-management",
    "project management": "project-management",
    "business development": "business-development",
    "general management": "general-management",
    "customer service": "customer-service",
    "supply chain management": "supply-chain-management",
    "scm": "supply-chain-management",
    "law": "law",
    "teaching": "teaching",
    "content writing": "content-writing",
}


def role_to_slug(role: str) -> str:
    """Map a role/domain to an Internshala slug without undefined variables."""
    normalized = re.sub(r"\s+", " ", str(role or "").lower().strip())
    if not normalized:
        return "software-development"
    if normalized in DOMAIN_SLUG_MAP:
        return DOMAIN_SLUG_MAP[normalized]
    for key, slug in DOMAIN_SLUG_MAP.items():
        if key in normalized or normalized in key:
            return slug
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return slug or "software-development"


def build_internshala_url(slug: str, listing_type: str) -> str:
    listing_type = listing_type.lower()
    if listing_type == "job":
        return f"{BASE}/jobs/{slug}-jobs"
    return f"{BASE}/internships/{slug}-internship"


class IntershalaPlatform(BasePlatform):
    async def login(self, page: Page) -> None:
        if INTERNSHALA_STATE_PATH.exists():
            logger.info("Internshala: using saved encrypted session.")
            return

        # A CI runner has no interactive browser for manual login. Failing fast
        # is safer than hanging a 45-minute workflow waiting for stdin.
        if os.environ.get("CI", "").lower() == "true":
            raise RuntimeError(
                "Internshala session is not configured for CI. "
                "Provide a valid encrypted browser state before running the agent."
            )

        logger.info("Opening Internshala for manual login...")
        await page.goto(f"{BASE}/login")
        print("\n[ACTION REQUIRED] Log in to Internshala in the browser window, then press ENTER.")
        input()
        state = await page.context.storage_state()
        INTERNSHALA_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        INTERNSHALA_STATE_PATH.write_bytes(encrypt(json.dumps(state)))
        logger.info("Internshala session saved.")

    def build_search_url(self, preferences: dict) -> list[str]:
        domain_value = preferences.get("domain")
        if domain_value:
            slug = role_to_slug(domain_value)
        else:
            slug = role_to_slug(preferences.get("primary_role", "Software Development"))

        listing_type = str(preferences.get("looking_for", "internship")).lower()
        if listing_type == "both":
            return [build_internshala_url(slug, "internship"), build_internshala_url(slug, "job")]
        return [build_internshala_url(slug, listing_type)]

    async def scrape_jobs(self, page: Page, search_url: str) -> list[dict]:
        return await scrape_jobs(page, search_url)

    async def apply(self, page: Page, job: dict, resume_summary: str, preferences_md: str, automation_mode: str = "semi_automated") -> dict:
        return await apply_to_job(page, job, resume_summary, preferences_md, automation_mode=automation_mode)
