"""Non-interactive runner used by GitHub Actions."""

import asyncio
import json
import os
from pathlib import Path

from src.core.agent import build_graph
from src.mcp.server import _build_state
from src.storage.resume_store import save_resume
from src.storage.database import export_to_csv
from src.utils.config import USER_PROFILE_PATH, DATA_DIR, MAX_APPLICATIONS_DEFAULT


def prepare_inputs() -> dict:
    raw_profile = os.environ.get("USER_PROFILE_JSON", "").strip()
    resume = os.environ.get("RESUME_TEXT", "")
    if not raw_profile:
        raise RuntimeError("USER_PROFILE_JSON secret is missing")
    if not resume:
        raise RuntimeError("RESUME_TEXT secret is missing")

    prefs = json.loads(raw_profile)
    if not isinstance(prefs, dict):
        raise RuntimeError("USER_PROFILE_JSON must contain a JSON object")

    prefs.pop("url", None)
    prefs["max_applications"] = min(
        max(1, int(os.environ.get("MAX_APPLICATIONS", prefs.get("max_applications", 10)))),
        MAX_APPLICATIONS_DEFAULT,
    )
    mode = os.environ.get("AUTOMATION_MODE", prefs.get("automation_mode", "semi_automated"))
    if mode not in {"fully_automated", "semi_automated"}:
        raise RuntimeError("AUTOMATION_MODE must be fully_automated or semi_automated")
    prefs["automation_mode"] = mode

    USER_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_PROFILE_PATH.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    save_resume(resume)
    return prefs


async def main() -> None:
    prefs = prepare_inputs()
    state = _build_state(prefs, prefs["max_applications"], prefs["automation_mode"])
    graph = build_graph()
    final_state = await graph.ainvoke(state)

    results = final_state.get("application_results", [])
    summary = {
        "run_id": os.environ.get("GITHUB_RUN_ID", "local"),
        "applied": sum(r.get("status") == "applied" for r in results),
        "skipped": sum(r.get("status") == "skipped" for r in results),
        "external": sum(r.get("status") == "external" for r in results),
        "already_applied": sum(r.get("status") == "already_applied" for r in results),
        "failed": sum(r.get("status") not in {"applied", "skipped", "external", "already_applied"} for r in results),
        "results": results,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "run_result.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    try:
        await export_to_csv(str(DATA_DIR / "applications_export.csv"))
    except Exception as exc:
        print(f"Warning: CSV export failed: {exc}")
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    asyncio.run(main())
