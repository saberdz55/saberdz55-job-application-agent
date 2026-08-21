"""Safe parsing and validation for LLM outputs."""

import json
import re
from typing import Any
from urllib.parse import urlparse

from src.utils.logger import get_logger

logger = get_logger("parsers")


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_json_safe(text: str, expected_type: type = list) -> Any:
    cleaned = _strip_code_fences(text)
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        match = re.search(r"\[.*\]" if expected_type is list else r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON found in LLM output: {exc}") from exc
        try:
            result = json.loads(match.group(0))
        except json.JSONDecodeError as nested:
            raise ValueError(f"Could not parse JSON from LLM output: {nested}") from nested
    if not isinstance(result, expected_type):
        raise ValueError(f"Expected {expected_type.__name__}, got {type(result).__name__}")
    return result


def validate_link_list(parsed: list) -> list[str]:
    valid: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            logger.warning("Ignoring non-string job link returned by LLM")
            continue
        try:
            parsed_url = urlparse(item)
            if parsed_url.scheme in {"http", "https"} and parsed_url.netloc:
                valid.append(item)
        except Exception:
            logger.warning("Ignoring malformed job URL returned by LLM")
    return valid


def validate_answer_list(parsed: list, expected_count: int) -> list[dict]:
    if len(parsed) != expected_count:
        raise ValueError(f"Answer count mismatch: got {len(parsed)}, expected {expected_count}")
    for item in parsed:
        if not isinstance(item, dict) or "question_id" not in item or "answer" not in item:
            raise ValueError(f"Answer item missing required keys: {item}")
    return parsed
