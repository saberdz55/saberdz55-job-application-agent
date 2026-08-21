"""LangGraph workflow for the autonomous job agent."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from langgraph.graph import StateGraph, END

from src.core.state import AgentState
from src.core.policy import job_hard_gate, looks_like_challenge
from src.storage.application_tracker import load_preferences_md
from src.storage.database import init_db, get_applied_links, insert_application
from src.storage.resume_store import save_resume_summary, load_resume_summary, resume_summary_exists
from src.llm.generator import generate_resume_summary, filter_jobs
from src.browser.manager import BrowserManager
from src.platforms.internshala import IntershalaPlatform
from src.platforms.naukri import NaukriPlatform
from src.platforms.naukri import STATE_PATH as NAUKRI_STATE_PATH
from src.utils.config import INTERNSHALA_STATE_PATH, LLM_BATCH_SIZE, MAX_APPLICATIONS_DEFAULT, WARN_THRESHOLD_RATIO, DATA_DIR
from src.utils.logger import get_logger

logger = get_logger("agent")
PLATFORM_CLASSES = {"internshala": IntershalaPlatform, "naukri": NaukriPlatform}
PLATFORM_STATE_PATHS = {"internshala": INTERNSHALA_STATE_PATH, "naukri": NAUKRI_STATE_PATH}


def _get_platform(name: str):
    cls = PLATFORM_CLASSES.get(name)
    if not cls:
        raise ValueError(f"Unknown platform: '{name}'. Available: {list(PLATFORM_CLASSES)}")
    return cls()


def _run_dir() -> Path:
    run_id = os.environ.get("GITHUB_RUN_ID") or datetime.now(timezone.utc).strftime("local-%Y%m%d-%H%M%S")
    path = DATA_DIR / "runs" / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _platform_raw_jobs_path(run_dir: Path, platform: str) -> Path:
    return run_dir / f"raw_jobs_{platform}.json"


def _platform_shortlisted_path(run_dir: Path, platform: str) -> Path:
    return run_dir / f"shortlisted_jobs_{platform}.json"


def _headless() -> bool:
    value = os.environ.get("AGENT_HEADLESS")
    if value is not None:
        return value.lower() not in {"0", "false", "no"}
    return os.environ.get("CI", "").lower() == "true"


def _normalize_result(result: dict) -> dict:
    """Turn known verification/LLM uncertainty into an explicit human-review state."""
    error = str(result.get("error") or "")
    if result.get("status") == "failed" and (
        "human review required" in error.lower() or looks_like_challenge(error)
    ):
        result["status"] = "needs_human"
    return result


async def node_load_persisted_data(state: AgentState) -> AgentState:
    logger.info("[Stage] Loading persisted data...")
    await init_db()
    resume_summary = state.get("resume_summary", "")
    if not resume_summary and resume_summary_exists():
        resume_summary = load_resume_summary()
        logger.info("Loaded existing resume summary.")
    return {**state, "resume_summary": resume_summary, "application_results": state.get("application_results", []), "stage": "data_loaded"}


async def node_generate_resume_summary(state: AgentState) -> AgentState:
    if state.get("resume_summary"):
        logger.info("[Stage] Resume summary already loaded — skipping.")
        return {**state, "stage": "summary_ready"}
    logger.info("[Stage] Generating resume summary...")
    summary = generate_resume_summary(state["resume_raw"])
    save_resume_summary(summary)
    return {**state, "resume_summary": summary, "stage": "summary_ready"}


async def node_run_platforms(state: AgentState) -> AgentState:
    platforms = state.get("platforms", ["internshala"])
    all_results = list(state.get("application_results", []))
    applied_links: set[str] = await get_applied_links()
    run_dir = _run_dir()
    logger.info("Run workspace: %s", run_dir)
    for platform_name in platforms:
        logger.info("Platform: %s", platform_name.upper())
        state = await _run_single_platform(state, platform_name, applied_links, all_results, run_dir)
        applied_links = await get_applied_links()
    return {**state, "application_results": all_results, "stage": "all_platforms_done", "run_dir": str(run_dir)}


async def _run_single_platform(state: AgentState, platform_name: str, applied_links: set[str], all_results: list, run_dir: Path) -> AgentState:
    platform = _get_platform(platform_name)
    state_path = PLATFORM_STATE_PATHS[platform_name]
    prefs = state["user_preferences"]
    headless = _headless()

    logger.info("[%s] Stage 1/5: login", platform_name)
    async with BrowserManager(state_path=state_path, headless=headless) as bm:
        page = await bm.new_page()
        await platform.login(page)
        await bm.save_state()

    logger.info("[%s] Stage 2/5: build search URLs", platform_name)
    search_urls = platform.build_search_url(prefs)
    logger.info("Built %d URL(s) for %s", len(search_urls), platform_name)

    logger.info("[%s] Stage 3/5: scrape", platform_name)
    raw_path = _platform_raw_jobs_path(run_dir, platform_name)
    scraped_jobs: list[dict] = []
    async with BrowserManager(state_path=state_path, headless=headless) as bm:
        page = await bm.new_page()
        for url in search_urls:
            jobs = await platform.scrape_jobs(page, url)
            scraped_jobs.extend(jobs)
            logger.info("  Scraped %d jobs", len(jobs))

    seen_links: set[str] = set()
    deduped: list[dict] = []
    for job in scraped_jobs:
        link = job.get("link")
        if link and link not in seen_links:
            seen_links.add(link)
            deduped.append(job)
    scraped_jobs = deduped
    raw_path.write_text(json.dumps(scraped_jobs, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Scraped %d fresh unique jobs from %s.", len(scraped_jobs), platform_name)

    logger.info("[%s] Stage 4/5: deterministic gate + AI match", platform_name)
    short_path = _platform_shortlisted_path(run_dir, platform_name)
    preferences_md = load_preferences_md()
    candidates: list[dict] = []
    blocked_count = 0
    for job in scraped_jobs:
        if job.get("link") in applied_links:
            continue
        allowed, reason = job_hard_gate(job, prefs)
        if allowed:
            candidates.append(job)
        else:
            blocked_count += 1
            logger.info("  Hard-gate blocked %s: %s", job.get("title", "unknown"), reason)

    logger.info("Hard gate kept %d/%d candidates and blocked %d.", len(candidates), len(scraped_jobs), blocked_count)
    shortlisted_links: set[str] = set()
    for i in range(0, len(candidates), LLM_BATCH_SIZE):
        batch = candidates[i:i + LLM_BATCH_SIZE]
        try:
            matched = filter_jobs(batch, preferences_md)
            shortlisted_links.update(matched)
            logger.info("  AI batch %d: %d matched", i // LLM_BATCH_SIZE + 1, len(matched))
        except Exception as exc:
            logger.error("  Filter batch error: %s", exc)

    link_map = {j["link"]: j for j in candidates if j.get("link")}
    shortlisted: list[dict] = []
    for link in shortlisted_links:
        job = link_map.get(link)
        if not job:
            continue
        allowed, reason = job_hard_gate(job, prefs)
        if allowed:
            shortlisted.append(job)
        else:
            logger.warning("  Post-LLM gate removed %s: %s", job.get("title", "unknown"), reason)

    shortlisted.sort(key=lambda j: (str(j.get("title", "")).lower(), str(j.get("company", "")).lower()))
    short_path.write_text(json.dumps(shortlisted, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Shortlisted %d jobs for %s.", len(shortlisted), platform_name)

    logger.info("[%s] Stage 5/5: apply", platform_name)
    max_apps = min(max(int(prefs.get("max_applications", MAX_APPLICATIONS_DEFAULT)), 1), MAX_APPLICATIONS_DEFAULT)
    warn_at = max(1, int(max_apps * WARN_THRESHOLD_RATIO))
    automation_mode = state.get("automation_mode", "semi_automated")
    resume_summary = state["resume_summary"]
    jobs_to_apply = [j for j in shortlisted if j.get("link") not in applied_links][:max_apps]
    if not jobs_to_apply:
        logger.info("No new jobs to apply to on %s.", platform_name)
        return state

    applied_count = 0
    async with BrowserManager(state_path=state_path, headless=headless) as bm:
        page = await bm.new_page()
        for job in jobs_to_apply:
            if applied_count == warn_at:
                logger.warning("%s: reached %d/%d (75%%) of the configured limit.", platform_name, warn_at, max_apps)
            result = _normalize_result(await platform.apply(page, job, resume_summary, preferences_md, automation_mode=automation_mode))
            all_results.append(result)
            await insert_application(
                platform=platform_name,
                job_title=job.get("title", "Unknown"),
                company=job.get("company", "Unknown"),
                link=job["link"],
                status=result["status"],
                error=result.get("error"),
                raw_questions=result.get("raw_questions"),
            )
            applied_count += 1
            logger.info("  [%s] %d/%d — %s: %s @ %s", platform_name, applied_count, len(jobs_to_apply), result["status"], job.get("title"), job.get("company"))

    return state


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node("load_data", node_load_persisted_data)
    graph.add_node("resume_summary", node_generate_resume_summary)
    graph.add_node("run_platforms", node_run_platforms)
    graph.set_entry_point("load_data")
    graph.add_edge("load_data", "resume_summary")
    graph.add_edge("resume_summary", "run_platforms")
    graph.add_edge("run_platforms", END)
    return graph.compile()
