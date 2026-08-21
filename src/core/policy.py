"""Deterministic safety and relevance gates around LLM decisions."""

import re
from urllib.parse import urlparse

SENSITIVE_TERMS = {
    "work authorization", "visa", "sponsorship", "citizenship", "nationality",
    "disability", "medical", "health", "pregnan", "gender", "race", "religion",
    "ethnicity", "age", "date of birth", "criminal", "conviction", "veteran",
    "salary expectation", "expected salary", "notice period", "relocation",
}

NEGATIVE_DOMAIN_TERMS = {
    "video editing", "marketing", "sales", "content writing", "social media",
    "graphic design", "customer service", "business development",
}


def _text(*values: object) -> str:
    return " ".join(str(v or "") for v in values).lower()


def job_hard_gate(job: dict, preferences: dict) -> tuple[bool, str]:
    """Reject obvious mismatches before the LLM is allowed to shortlist."""
    haystack = _text(job.get("title"), job.get("description"), job.get("company"))
    for term in preferences.get("additional_preferences", "").lower().split(","):
        term = term.strip()
        if term and ("do not" in term or "no " in term):
            continue

    explicit = _text(preferences.get("additional_preferences"))
    for banned in NEGATIVE_DOMAIN_TERMS:
        if banned in haystack and banned in explicit:
            return False, f"blocked-domain:{banned}"

    roles = [preferences.get("primary_role", "")]
    roles.extend(preferences.get("other_roles", []) if isinstance(preferences.get("other_roles", []), list) else [])
    role_tokens = [r.strip().lower() for r in roles if str(r).strip()]
    if role_tokens and not any(r in haystack for r in role_tokens):
        # Allow core AI/ML synonyms for the user's stated AI/ML roles.
        ai_terms = {"ai", "artificial intelligence", "machine learning", "ml", "agentic", "data scientist", "data science"}
        if not any(t in haystack for t in ai_terms if any(t in r for r in role_tokens)):
            return False, "role-mismatch"

    locations = preferences.get("preferred_locations", [])
    work_mode = str(preferences.get("work_mode", "both")).lower()
    location_text = _text(job.get("location"))
    if locations and work_mode not in {"remote", "both"}:
        if not any(str(loc).lower() in location_text for loc in locations):
            return False, "location-mismatch"

    return True, "ok"


def question_requires_human(question: str, preferences: dict) -> tuple[bool, str]:
    """Do not let an LLM invent answers to consequential personal questions."""
    q = _text(question)
    if any(term in q for term in SENSITIVE_TERMS):
        # Only permit exact facts that are explicitly supplied by the user.
        supplied = _text(preferences.get("application_facts"), preferences.get("work_authorization"), preferences.get("notice_period"), preferences.get("salary_expectation"))
        if not supplied or not any(term in supplied for term in SENSITIVE_TERMS):
            return True, "sensitive-or-user-specific-question"
    return False, "safe"


def validate_url(url: str, allowed_hosts: set[str] | None = None) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        if allowed_hosts is not None and parsed.hostname not in allowed_hosts:
            return False
        return True
    except Exception:
        return False


def looks_like_challenge(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", _text(text))
    challenge_terms = ("captcha", "verify you are human", "security check", "robot check", "unusual activity", "verification required")
    return any(term in normalized for term in challenge_terms)
