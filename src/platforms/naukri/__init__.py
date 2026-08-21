"""Naukri platform integration."""

import json
import os
from playwright.async_api import Page

from src.platforms.base import BasePlatform
from src.platforms.naukri.scraper import scrape_jobs, construct_naukri_url
from src.platforms.naukri.applier import apply_to_job
from src.utils.config import CONFIGS_DIR, encrypt
from src.utils.logger import get_logger
from src.core.policy import looks_like_challenge

logger = get_logger("naukri")
STATE_PATH = CONFIGS_DIR / "naukri_state.enc"


class NaukriPlatform(BasePlatform):
    async def login(self, page: Page) -> None:
        if STATE_PATH.exists():
            await page.goto("https://www.naukri.com/", wait_until="domcontentloaded")
            body = (await page.locator("body").inner_text())[:8000]
            if looks_like_challenge(body):
                raise RuntimeError("Naukri security verification detected; human action is required.")
            if await page.locator("input[type='password']").count() > 0 and "login" in page.url.lower():
                raise RuntimeError("Naukri session expired; refresh the encrypted session before running.")
            logger.info("Naukri: verified saved encrypted session.")
            return

        if os.environ.get("CI", "").lower() == "true":
            raise RuntimeError("Naukri session is not configured for CI. Add NAUKRI_STATE_B64 and ENCRYPTION_KEY secrets.")

        logger.info("Opening Naukri for manual login...")
        await page.goto("https://www.naukri.com/", wait_until="domcontentloaded")
        print("\n[ACTION REQUIRED] Log in to Naukri in the browser window, then press ENTER.")
        input()
        state = await page.context.storage_state()
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_bytes(encrypt(json.dumps(state)))
        logger.info("Naukri session saved.")

    def build_search_url(self, preferences: dict) -> list[str]:
        primary = preferences.get("primary_role", "software developer")
        others = preferences.get("other_roles", [])
        job_titles = [primary] + (others if isinstance(others, list) else [])
        experience = max(0, int(preferences.get("experience_years", 0)))
        listing_type = str(preferences.get("looking_for", "job")).lower()
        if listing_type == "both":
            return [*[construct_naukri_url(title, experience, "job") for title in job_titles], *[construct_naukri_url(title, experience, "internship") for title in job_titles]]
        return [construct_naukri_url(title, experience, listing_type) for title in job_titles]

    async def scrape_jobs(self, page: Page, search_url: str) -> list[dict]:
        return await scrape_jobs(page, search_url)

    async def apply(self, page: Page, job: dict, resume_summary: str, preferences_md: str, automation_mode: str = "semi_automated") -> dict:
        return await apply_to_job(page, job, resume_summary, preferences_md, automation_mode)
