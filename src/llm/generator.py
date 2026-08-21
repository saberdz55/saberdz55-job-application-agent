"""Gemini-backed generation with deterministic validation gates."""

import json
from google import genai

from src.utils.config import GEMINI_API_KEY, GEMINI_MODEL, LLM_RETRY_LIMIT
from src.utils.logger import get_logger
from src.llm.prompts import DOMAIN_CLASSIFICATION_PROMPT, RESUME_SUMMARY_PROMPT, JOB_FILTER_PROMPT, APPLICATION_ANSWER_PROMPT, STRICT_JSON_RETRY_PROMPT, CHATBOT_QUESTION_PROMPT
from src.llm.parsers import parse_json_safe, validate_link_list, validate_answer_list
from src.core.policy import guard_questions, question_requires_human, HumanReviewRequired

logger = get_logger("llm")
client = genai.Client(api_key=GEMINI_API_KEY, vertexai=False)


def _call(prompt: str) -> str:
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("LLM returned an empty response")
    return text


def _call_with_json_retry(prompt: str, validator_fn, schema_description: str, task_description: str, expected_type: type = list, **validator_kwargs):
    last_error = None
    current_prompt = prompt
    for attempt in range(1, LLM_RETRY_LIMIT + 1):
        try:
            raw = _call(current_prompt)
            parsed = parse_json_safe(raw, expected_type=expected_type)
            return validator_fn(parsed, **validator_kwargs)
        except ValueError as exc:
            last_error = exc
            logger.warning("LLM JSON validation failed (%d/%d): %s", attempt, LLM_RETRY_LIMIT, exc)
            current_prompt = STRICT_JSON_RETRY_PROMPT.format(original_task=task_description, schema_description=schema_description)
    raise RuntimeError(f"LLM failed to produce valid JSON after {LLM_RETRY_LIMIT} attempts: {last_error}")


def classify_domain(role: str) -> str:
    return _call(DOMAIN_CLASSIFICATION_PROMPT.format(role=role)).strip().strip('"').strip("'")


def generate_resume_summary(resume_text: str) -> str:
    return _call(RESUME_SUMMARY_PROMPT.format(resume=resume_text))


def filter_jobs(jobs_batch: list[dict], preferences_md: str) -> list[str]:
    prompt = JOB_FILTER_PROMPT.format(preferences=preferences_md, jobs_json=json.dumps(jobs_batch, indent=2, ensure_ascii=False))
    return _call_with_json_retry(prompt, validate_link_list, 'Array of URL strings e.g. ["https://..."]', "Return matching job links as a JSON array of strings.")


def generate_answers(questions: list[dict], resume_summary: str, preferences_md: str, job_title: str, company: str, description: str) -> list[dict]:
    # A model must never be asked to guess a consequential personal fact.
    # application_facts are deliberately supplied separately from the LLM prompt.
    guard_questions(questions, {})
    prompt = APPLICATION_ANSWER_PROMPT.format(
        resume_summary=resume_summary,
        job_title=job_title,
        company=company,
        description=description,
        preferences_md=preferences_md,
        questions_json=json.dumps(questions, indent=2, ensure_ascii=False),
    )
    return _call_with_json_retry(
        prompt, validate_answer_list,
        'Array of {question_id, answer} objects',
        "Generate answers for each application question as a JSON array.",
        expected_count=len(questions),
    )


def answer_chatbot_question(question: str, options: list[str], history: list, job_title: str, company: str, description: str, resume_summary: str, preferences_md: str) -> str:
    needs_human, reason = question_requires_human(question, {})
    if needs_human:
        raise HumanReviewRequired(f"Human review required: {reason}: {question}")

    history_lines = []
    for msg in history:
        opts = f" (options: {', '.join(msg.options)})" if msg.options else ""
        history_lines.extend([f"  Q: {msg.question}{opts}", f"  A: {msg.answer}"])
    history_text = "\n".join(history_lines) if history_lines else "None — this is the first question."
    options_text = "Options (you MUST pick one exactly):\n" + "\n".join(f"  - {o}" for o in options) if options else "(Free text — write a short professional answer)"

    prompt = CHATBOT_QUESTION_PROMPT.format(
        job_title=job_title, company=company, description=description[:800],
        resume_summary=resume_summary, preferences_md=preferences_md,
        history_text=history_text, question=question, options_block=options_text,
    )
    answer = _call(prompt).strip().strip('"').strip("'")
    if not options:
        return answer

    options_lower = {o.lower(): o for o in options}
    if answer.lower() in options_lower:
        return options_lower[answer.lower()]
    for lower_opt, original_opt in options_lower.items():
        if lower_opt in answer.lower() or answer.lower() in lower_opt:
            logger.warning("Normalized LLM option answer to a supplied option")
            return original_opt
    raise HumanReviewRequired(f"LLM answer did not exactly match supplied options: {answer!r}")
