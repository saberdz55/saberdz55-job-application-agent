# Authenticated job-platform sessions

The agent reuses Playwright `storageState` so CI does not need to perform a password login on every run. Playwright documents that this state can contain cookies and other credentials and should never be committed to a repository. citeturn1search1

## 1. Create a local encrypted session

From the repository root:

```bash
python scripts/prepare_session.py naukri
python scripts/prepare_session.py internshala
```

Run only the platform(s) you actually use. The browser opens locally; complete the normal login flow yourself. Do not attempt to bypass CAPTCHA, MFA, security checks, or platform restrictions.

Each command creates an ignored file under `data/session-secrets/` containing the encrypted session as base64.

## 2. Keep one encryption key

The same `ENCRYPTION_KEY` must be used when the session was encrypted and when CI decrypts it. Local development creates one in `.env` if necessary. Copy the value into GitHub Actions Secrets; never commit `.env`.

## 3. Add GitHub Actions secrets

Add:

- `ENCRYPTION_KEY`
- `GEMINI_API_KEY`
- `USER_PROFILE_JSON`
- `RESUME_TEXT`
- `NAUKRI_STATE_B64` (if using Naukri)
- `INTERNSHALA_STATE_B64` (if using Internshala)

GitHub encrypts Actions secrets and recommends least-privilege credentials. Secrets are also subject to a 48 KB size limit. citeturn1search0turn1search2

## 4. Run the agent

Use the `Autonomous Job Agent` workflow. Start with `1` application and `semi_automated` mode. Increase capacity only after a successful end-to-end run.

## Session lifecycle

The workflow restores the encrypted state only for the current runner, verifies the platform session before scraping, and deletes the session files at the end of the job. Expired sessions fail closed instead of silently falling back to a new unauthenticated account.

A CAPTCHA, security verification, or unknown consequential application question is treated as `needs_human`; the agent does not bypass it or invent an answer.
