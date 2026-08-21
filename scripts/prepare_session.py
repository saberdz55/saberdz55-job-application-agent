"""Create an encrypted platform session locally and export a CI-safe base64 blob.

Usage:
    python scripts/prepare_session.py naukri
    python scripts/prepare_session.py internshala

The exported file is ignored by git. Never paste its contents into source code.
"""

import argparse
import asyncio
import base64
from pathlib import Path

from src.browser.manager import BrowserManager
from src.platforms.naukri import NaukriPlatform, STATE_PATH as NAUKRI_STATE
from src.platforms.internshala import IntershalaPlatform
from src.utils.config import INTERNSHALA_STATE_PATH

PLATFORMS = {
    "naukri": (NaukriPlatform, NAUKRI_STATE),
    "internshala": (IntershalaPlatform, INTERNSHALA_STATE_PATH),
}


async def main(platform_name: str) -> None:
    cls, state_path = PLATFORMS[platform_name]
    async with BrowserManager(state_path=state_path, headless=False) as browser:
        page = await browser.new_page()
        await cls().login(page)
        await browser.save_state()

    output = Path("data") / "session-secrets" / f"{platform_name}_state.b64"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(base64.b64encode(state_path.read_bytes()).decode("ascii"), encoding="ascii")
    print(f"Session ready: {output}")
    print("Add this file's value as the matching GitHub Actions secret; do not commit it.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("platform", choices=sorted(PLATFORMS))
    args = parser.parse_args()
    asyncio.run(main(args.platform))
