"""Non-interactive runner used by GitHub Actions and local smoke runs."""

import asyncio
import json
import os

from src.core.agent import build_graph
from src.mcp.server import _build_state
from src.storage.application_tracker import save_preferences_md
from src.storage.resume_store import save_resume
from src.storage.database import export_to_csv
from src.utils.config import USER_PROFILE_PATH, DATA_DIR, MAX_APPLICATIONS_DEFAULT
from src.browser.session_vault import restore_sessions_from_env


def prepare_inputs() -> dict:
    raw_profile = os.environ.get("USER_PROFILE_JSON", "").strip()
    resume = os.environ.get("RESUME_TEXT", "")
    if not raw_profile:
        raise RuntimeError("USER_PROFILE_JSON secret is missing")
    if not resume:
        raise RuntimeError("RESUME_TEXT secret is missing")

    try:
        prefs = json.loads(raw_profile)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"USER_PROFILE_JSON is invalid JSON: {exc}") from exc
    if not isinstance(prefs, dict):
        raise RuntimeError("USER_PROFILE_JSON must contain a JSON object")

    prefs.pop("url", None)
    try:
        requested_max = int(os.environ.get("MAX_APPLICATIONS", prefs.get("max_applications", 10)))
    except ValueError as exc:
        raise RuntimeError("MAX_APPLICATIONS must be an integer") from exc
    prefs["max_applications"] = min(max(1, requested_max), MAX_APPLICATIONS_DEFAULT)

    mode = os.environ.get("AUTOMATION_MODE", prefs.get("automation_mode", "semi_automated"))
    if mode not in {"fully_automated", "semi_automated"}:
        raise RuntimeError("AUTOMATION_MODE must be fully_automated or semi_automated")
    prefs["automation_mode"] = mode

    platforms = prefs.get("platforms", ["naukri"])
    if not isinstance(platforms, list) or not platforms:
        raise RuntimeError("platforms must be a non-empty array")
    prefs["platforms"] = [str(p).lower().strip() for p in platforms]

    USER_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_PROFILE_PATH.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")
    save_preferences_md(prefs)
    save_resume(resume)
    return prefs


async def main() -> None:
    # Restore encrypted browser state before the first browser context is created.
    restore_sessions_from_env()
    prefs = prepare_inputs()
    state = _build_state(prefs, prefs["max_applications"], prefs["automation_mode"])
    graph = build_graph()
    final_state = await graph.ainvoke(state)

    results = final_state.get("application_results", [])
    terminal = {"applied", "skipped", "external", "already_applied", "needs_human", "blocked"}
    summary = {
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "applied": sum(r.get("status") == "applied" for r in results),
        "skipped": sum(r.get("status") == "skipped" for r in results),
        "external": sum(r.get("status") == "external" for r in results),
        "already_applied": sum(r.get("status") == "already_applied" for r in results),
        "needs_human": sum(r.get("status") == "needs_human" for r in results),
        "blocked": sum(r.get("status") == "blocked" for r in results),
        "failed": sum(r.get("status") not in terminal for r in results),
        "results": results,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "run_result.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    try:
        await export_to_csv(str(DATA_DIR / "applications_export.csv"))
    except Exception as exc:
        print(f"Warning: CSV export failed: {exc}")
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    asyncio.run(main())
