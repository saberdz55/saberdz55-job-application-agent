"""Central runtime configuration and cryptographic primitives."""

import os
from pathlib import Path
from dotenv import load_dotenv
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
LOGS_DIR = ROOT / "logs"
CONFIGS_DIR = ROOT / "configs"
RESUMES_DIR = DATA_DIR / "resumes"
USER_PROFILE_PATH = DATA_DIR / "user_profile.json"
RAW_JOBS_PATH = DATA_DIR / "raw_jobs.json"
SHORTLISTED_JOBS_PATH = DATA_DIR / "shortlisted_jobs.json"
APPLICATIONS_DB_PATH = DATA_DIR / "applications.db"
PREFERENCES_PATH = DATA_DIR / "preferences.md"
RESUME_RAW_PATH = RESUMES_DIR / "resume.md"
RESUME_SUMMARY_PATH = RESUMES_DIR / "resume_summary.md"
INTERNSHALA_STATE_PATH = CONFIGS_DIR / "internshala_state.enc"

for directory in (DATA_DIR, LOGS_DIR, CONFIGS_DIR, RESUMES_DIR):
    directory.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")


def _load_fernet() -> Fernet:
    key = os.environ.get("ENCRYPTION_KEY", "").strip()
    if key:
        try:
            return Fernet(key.encode())
        except Exception as exc:
            raise RuntimeError("ENCRYPTION_KEY is invalid") from exc

    # Never silently generate a new key in CI: doing so would make previously
    # encrypted browser sessions unrecoverable and can create a false sense of safety.
    if os.environ.get("CI", "").lower() == "true":
        raise RuntimeError("ENCRYPTION_KEY secret is required in CI")

    generated = Fernet.generate_key().decode()
    env_path = ROOT / ".env"
    existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = existing.splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.startswith("ENCRYPTION_KEY="):
            lines[index] = f"ENCRYPTION_KEY={generated}"
            replaced = True
            break
    if not replaced:
        lines.append(f"ENCRYPTION_KEY={generated}")
    env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    os.environ["ENCRYPTION_KEY"] = generated
    return Fernet(generated.encode())


FERNET = _load_fernet()


def encrypt(data: str) -> bytes:
    return FERNET.encrypt(data.encode("utf-8"))


def decrypt(data: bytes) -> str:
    return FERNET.decrypt(data).decode("utf-8")


MAX_APPLICATIONS_DEFAULT = 20
WARN_THRESHOLD_RATIO = 0.75
LLM_BATCH_SIZE = 10
LLM_RETRY_LIMIT = 3
TYPING_DELAY_MIN = 0.04
TYPING_DELAY_MAX = 0.12
ACTION_DELAY_MIN = 0.5
ACTION_DELAY_MAX = 2.0
PAGE_LOAD_WAIT = 3.0
