"""Prompt templates kept separate from execution logic."""

DOMAIN_CLASSIFICATION_PROMPT = """
Classify the job role "{role}" into exactly one allowed domain:
Software Development, Data Science, Artificial Intelligence (AI), Machine Learning,
Cloud Computing, Cyber Security, Information Technology, Engineering, Design,
Digital Marketing, Marketing, Sales, Finance, Human Resources (HR), Operations,
Product Management, Project Management, Business Development, General Management,
Customer Service, Supply Chain Management (SCM), Law, Teaching, Content Writing.
Return only the domain name.
"""

RESUME_SUMMARY_PROMPT = """
Summarize this resume in at most 400 words. Include only facts explicitly present:
skills, education, experience, projects, certifications and achievements.
Never infer or invent employment, years, salary, authorization, location or availability.
RESUME:
{resume}
Return only the summary.
"""

JOB_FILTER_PROMPT = """
Evaluate these jobs against the user's preferences.

USER PREFERENCES:
{preferences}

JOBS (JSON):
{jobs_json}

Return a JSON array containing only links that clearly satisfy the preferences.
Rules:
- Never override explicit exclusions.
- Do not treat a borderline match as a match.
- Match role/domain, experience, work mode, location and compensation when stated.
- If important information is missing, exclude the job rather than guess.
- Return only valid JSON, no markdown or explanation.
"""

APPLICATION_ANSWER_PROMPT = """
Fill an application using only verified facts from the supplied resume summary and preferences.
Never invent experience, dates, salary, authorization, sponsorship, availability, location, education or personal information.

RESUME SUMMARY:
{resume_summary}
JOB DETAILS:
Title: {job_title}
Company: {company}
Description: {description}
USER PREFERENCES:
{preferences_md}
QUESTIONS:
{questions_json}

Return the same number of objects in the same order:
{{"question_id": <id>, "answer": <answer>}}
Rules:
- Radio/select: choose exactly one supplied option only when the answer is supported by known facts.
- Checkbox: include only options supported by known facts.
- Text: concise, professional and factual.
- Never guess a consequential personal fact. If the question cannot be answered from supplied facts, stop rather than fabricate.
- Return only valid JSON.
"""

CHATBOT_QUESTION_PROMPT = """
Answer one live job-application question using only verified applicant facts.
Never invent experience, dates, authorization, sponsorship, salary, availability or other personal facts.

JOB:
Title: {job_title}
Company: {company}
Description: {description}

APPLICANT SUMMARY:
{resume_summary}
PREFERENCES:
{preferences_md}
HISTORY:
{history_text}

QUESTION:
{question}
{options_block}

If options are supplied, return exactly one supplied option. If the answer is not supported by verified facts, do not guess.
For safe free-text questions, return one concise professional answer and nothing else.
"""

STRICT_JSON_RETRY_PROMPT = """
The previous response was invalid JSON.
Task: {original_task}
Schema: {schema_description}
Return ONLY valid JSON. No markdown, explanation or preamble.
"""
