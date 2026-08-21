"""Deterministic safety and relevance gates around LLM decisions."""

import re
from urllib.parse import urlparse

SENSITIVE_TERMS = {
    "work authorization", "visa", "sponsorship", "citizenship", "nationality",
    "disability", "medical", "health", "pregnan", "gender", "race", "religion",
    "ethnicity", "age", "date of birth", "criminal", "conviction", "veteran",
    "salary expectation", "expected salary", "notice period", "relocation",
}
NEGATIVE_DOMAIN_TERMS = {"video editing", "marketing", "sales", "content writing", "social media", "graphic design", "customer service", "business development"}


class HumanReviewRequired(RuntimeError):
    """Raised when automation would require inventing or guessing a user fact."""


def _text(*values: object) -> str:
    return " ".join(str(v or "") for v in values).lower()


def job_hard_gate(job: dict, preferences: dict) -> tuple[bool, str]:
    haystack = _text(job.get("title"), job.get("description"), job.get("company"))
    explicit = _text(preferences.get("additional_preferences"))
    for banned in NEGATIVE_DOMAIN_TERMS:
        if banned in haystack and banned in explicit:
            return False, f"blocked-domain:{banned}"

    roles = [preferences.get("primary_role", "")]
    roles.extend(preferences.get("other_roles", []) if isinstance(preferences.get("other_roles", []), list) else [])
    role_tokens = [str(r).strip().lower() for r in roles if str(r).strip()]
    if role_tokens and not any(r in haystack for r in role_tokens):
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
    q = _text(question)
    if any(term in q for term in SENSITIVE_TERMS):
        supplied = _text(preferences.get("application_facts"), preferences.get("work_authorization"), preferences.get("notice_period"), preferences.get("salary_expectation"))
        if not supplied:
            return True, "sensitive-or-user-specific-question"
    return False, "safe"


def guard_questions(questions: list[dict], preferences: dict) -> None:
    """Stop before filling a form when a consequential answer is unknown."""
    for question in questions:
        needs_human, reason = question_requires_human(str(question.get("question", "")), preferences)
        if needs_human:
            raise HumanReviewRequired(f"Human review required for question: {question.get('question', '')} ({reason})")


def validate_url(url: str, allowed_hosts: set[str] | None = None) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        return allowed_hosts is None or parsed.hostname in allowed_hosts
    except Exception:
        return False


def looks_like_challenge(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", _text(text))
    return any(term in normalized for term in ("captcha", "verify you are human", "security check", "robot check", "unusual activity", "verification required"))
