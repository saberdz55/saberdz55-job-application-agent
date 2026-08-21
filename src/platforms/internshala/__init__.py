"""Internshala platform integration."""

import json
import os
import re

from playwright.async_api import Page

from src.platforms.base import BasePlatform
from src.platforms.internshala.scraper import scrape_jobs
from src.platforms.internshala.applier import apply_to_job
from src.utils.config import INTERNSHALA_STATE_PATH, encrypt
from src.utils.logger import get_logger
from src.core.policy import looks_like_challenge

logger = get_logger("internshala")
BASE = "https://internshala.com"

DOMAIN_SLUG_MAP = {
    "software development": "software-development", "software developer": "software-development",
    "software engineering": "software-development", "data science": "data-science",
    "data scientist": "data-science", "artificial intelligence": "artificial-intelligence",
    "ai": "artificial-intelligence", "machine learning": "machine-learning",
    "cloud computing": "cloud-computing", "cyber security": "cyber-security",
    "information technology": "information-technology", "engineering": "engineering",
    "design": "design", "digital marketing": "digital-marketing", "marketing": "marketing",
    "sales": "sales", "finance": "finance", "human resources": "human-resources", "hr": "human-resources",
    "operations": "operations", "product management": "product-management", "project management": "project-management",
    "business development": "business-development", "general management": "general-management",
    "customer service": "customer-service", "supply chain management": "supply-chain-management", "scm": "supply-chain-management",
    "law": "law", "teaching": "teaching", "content writing": "content-writing",
}


def role_to_slug(role: str) -> str:
    normalized = re.sub(r"\s+", " ", str(role or "").lower().strip())
    if not normalized:
        return "software-development"
    if normalized in DOMAIN_SLUG_MAP:
        return DOMAIN_SLUG_MAP[normalized]
    for key, slug in DOMAIN_SLUG_MAP.items():
        if key in normalized or normalized in key:
            return slug
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-") or "software-development"


def build_internshala_url(slug: str, listing_type: str) -> str:
    return f"{BASE}/jobs/{slug}-jobs" if listing_type.lower() == "job" else f"{BASE}/internships/{slug}-internship"


class IntershalaPlatform(BasePlatform):
    async def login(self, page: Page) -> None:
        if INTERNSHALA_STATE_PATH.exists():
            await page.goto(BASE, wait_until="domcontentloaded")
            body = (await page.locator("body").inner_text())[:8000]
            if looks_like_challenge(body):
                raise RuntimeError("Internshala security verification detected; human action is required.")
            if await page.locator("input[type='password']").count() > 0 and "login" in page.url.lower():
                raise RuntimeError("Internshala session expired; refresh the encrypted session before running.")
            logger.info("Internshala: verified saved encrypted session.")
            return

        if os.environ.get("CI", "").lower() == "true":
            raise RuntimeError("Internshala session is not configured for CI. Add INTERNSHALA_STATE_B64 and ENCRYPTION_KEY secrets.")

        logger.info("Opening Internshala for manual login...")
        await page.goto(f"{BASE}/login", wait_until="domcontentloaded")
        print("\n[ACTION REQUIRED] Log in to Internshala in the browser window, then press ENTER.")
        input()
        state = await page.context.storage_state()
        INTERNSHALA_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        INTERNSHALA_STATE_PATH.write_bytes(encrypt(json.dumps(state)))
        logger.info("Internshala session saved.")

    def build_search_url(self, preferences: dict) -> list[str]:
        domain_value = preferences.get("domain") or preferences.get("primary_role", "Software Development")
        slug = role_to_slug(domain_value)
        listing_type = str(preferences.get("looking_for", "internship")).lower()
        if listing_type == "both":
            return [build_internshala_url(slug, "internship"), build_internshala_url(slug, "job")]
        return [build_internshala_url(slug, listing_type)]

    async def scrape_jobs(self, page: Page, search_url: str) -> list[dict]:
        return await scrape_jobs(page, search_url)

    async def apply(self, page: Page, job: dict, resume_summary: str, preferences_md: str, automation_mode: str = "semi_automated") -> dict:
        return await apply_to_job(page, job, resume_summary, preferences_md, automation_mode=automation_mode)
