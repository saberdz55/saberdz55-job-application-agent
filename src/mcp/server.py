"""MCP control server for the autonomous job application agent.

This layer does not replace the existing LangGraph/Playwright workflow. It exposes
small, safe control tools so an MCP-capable client can start a run and inspect it.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from mcp.server.fastmcp import FastMCP

from src.core.agent import build_graph
from src.core.state import AgentState
from src.storage.database import APPLICATIONS_DB_PATH, init_db
from src.storage.resume_store import load_resume
from src.utils.config import USER_PROFILE_PATH, MAX_APPLICATIONS_DEFAULT

mcp = FastMCP(
    "job-application-agent",
    instructions=(
        "Control the autonomous job application workflow. "
        "Never claim an application was submitted unless the tool result says so. "
        "Use get_status and get_history to verify outcomes."
    ),
)

_run_lock = asyncio.Lock()
_run_task: asyncio.Task | None = None
_run_state: dict[str, Any] = {
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "error": None,
    "results": [],
}


def _load_saved_preferences() -> dict:
    if not USER_PROFILE_PATH.exists():
        raise RuntimeError(
            "No saved profile found. Run the existing setup once (python -m src.main) "
            "to configure resume, preferences, platforms and automation mode."
        )
    prefs = json.loads(USER_PROFILE_PATH.read_text(encoding="utf-8"))
    prefs.pop("url", None)
    return prefs


def _build_state(prefs: dict, max_applications: int | None, automation_mode: str | None) -> AgentState:
    resume = load_resume()
    prefs = dict(prefs)
    if max_applications is not None:
        prefs["max_applications"] = max(1, min(int(max_applications), MAX_APPLICATIONS_DEFAULT))
    if automation_mode is not None:
        if automation_mode not in {"fully_automated", "semi_automated"}:
            raise ValueError("automation_mode must be fully_automated or semi_automated")
        prefs["automation_mode"] = automation_mode

    platforms = prefs.get("platforms", ["internshala"])
    if not platforms:
        raise ValueError("No job platforms are configured in the saved profile")

    return {
        "user_preferences": prefs,
        "resume_raw": resume,
        "resume_summary": "",
        "search_url": "",
        "scraped_jobs": [],
        "shortlisted_jobs": [],
        "applied_job_links": set(),
        "current_job_index": 0,
        "application_results": [],
        "stage": "init",
        "error": None,
        "platform": platforms[0],
        "platforms": platforms,
        "current_platform_index": 0,
        "automation_mode": prefs.get("automation_mode", "semi_automated"),
    }


async def _execute_run(max_applications: int | None, automation_mode: str | None) -> None:
    global _run_state
    try:
        prefs = _load_saved_preferences()
        state = _build_state(prefs, max_applications, automation_mode)
        graph = build_graph()
        final_state = await graph.ainvoke(state)
        _run_state.update(
            status="completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            error=None,
            results=final_state.get("application_results", []),
        )
    except asyncio.CancelledError:
        _run_state.update(
            status="cancelled",
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        raise
    except Exception as exc:
        _run_state.update(
            status="failed",
            finished_at=datetime.now(timezone.utc).isoformat(),
            error=f"{type(exc).__name__}: {exc}",
        )


@mcp.tool()
async def start_auto_apply(
    max_applications: int = 10,
    automation_mode: str = "fully_automated",
) -> dict[str, Any]:
    """Start the existing job-search/filter/apply workflow in the background."""
    global _run_task, _run_state
    if _run_task and not _run_task.done():
        return {"status": "already_running", **_run_state}

    await init_db()
    async with _run_lock:
        if _run_task and not _run_task.done():
            return {"status": "already_running", **_run_state}
        _run_state = {
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "error": None,
            "results": [],
        }
        _run_task = asyncio.create_task(_execute_run(max_applications, automation_mode))

    return {
        "status": "started",
        "message": "Job application workflow started.",
        "max_applications": max_applications,
        "automation_mode": automation_mode,
    }


@mcp.tool()
async def get_status() -> dict[str, Any]:
    """Return the current workflow status and latest results."""
    return dict(_run_state)


@mcp.tool()
async def get_history(limit: int = 20) -> list[dict[str, Any]]:
    """Return recent application records from the existing SQLite tracker."""
    await init_db()
    limit = max(1, min(int(limit), 100))
    import aiosqlite

    async with aiosqlite.connect(APPLICATIONS_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT platform, job_title, company, link, status, applied_at, error "
            "FROM applications ORDER BY applied_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


@mcp.tool()
async def stop_auto_apply() -> dict[str, Any]:
    """Stop the currently running workflow task, if one exists."""
    global _run_task
    if not _run_task or _run_task.done():
        return {"status": "not_running"}
    _run_task.cancel()
    return {"status": "stopping"}


if __name__ == "__main__":
    mcp.run()
