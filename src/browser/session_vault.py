"""Secure session bootstrap for CI runners.

Browser storage state is sensitive: it can impersonate an authenticated account.
The workflow therefore receives only an encrypted, base64-encoded blob as a
GitHub secret and materializes it for the duration of one run.
"""

import base64
import os
from pathlib import Path

from src.utils.config import CONFIGS_DIR
from src.utils.logger import get_logger

logger = get_logger("session-vault")

SESSION_ENV = {
    "naukri": ("NAUKRI_STATE_B64", CONFIGS_DIR / "naukri_state.enc"),
    "internshala": ("INTERNSHALA_STATE_B64", CONFIGS_DIR / "internshala_state.enc"),
}


def restore_sessions_from_env() -> dict[str, bool]:
    """Materialize encrypted browser states supplied by CI secrets."""
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    restored: dict[str, bool] = {}
    for platform, (env_name, path) in SESSION_ENV.items():
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            restored[platform] = path.exists()
            continue
        try:
            blob = base64.b64decode(raw, validate=True)
            if len(blob) < 32:
                raise ValueError("session blob is unexpectedly small")
            path.write_bytes(blob)
            restored[platform] = True
            logger.info("Restored encrypted %s browser session.", platform)
        except Exception as exc:
            raise RuntimeError(f"Invalid {env_name} secret: {exc}") from exc
    return restored


def session_status(platform: str) -> dict:
    """Return non-sensitive local session metadata; never expose cookies."""
    _, path = SESSION_ENV[platform]
    return {"platform": platform, "present": path.exists(), "bytes": path.stat().st_size if path.exists() else 0}
