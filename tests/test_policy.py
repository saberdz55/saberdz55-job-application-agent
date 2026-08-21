import unittest

from src.core.policy import HumanReviewRequired, guard_questions, job_hard_gate, looks_like_challenge


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.prefs = {
            "primary_role": "AI ML Engineer",
            "other_roles": ["Agentic AI Developer", "AI Engineer", "Data Scientist"],
            "preferred_locations": ["Bangalore", "Kerala"],
            "work_mode": "both",
            "additional_preferences": "STRICTLY DO NOT SELECT JOBS FROM ANY OTHER DOMAIN. NO VIDEO EDITING, NO MARKETING, NO SALES",
        }

    def test_blocks_explicit_forbidden_domain(self):
        ok, reason = job_hard_gate({"title": "Video Editor", "description": "AI video editing", "location": "Bangalore"}, self.prefs)
        self.assertFalse(ok)
        self.assertIn("blocked-domain", reason)

    def test_allows_ai_engineering_role(self):
        ok, _ = job_hard_gate({"title": "AI Engineer", "description": "Build ML systems", "location": "Bangalore"}, self.prefs)
        self.assertTrue(ok)

    def test_sensitive_question_requires_human(self):
        with self.assertRaises(HumanReviewRequired):
            guard_questions([{"question": "Will you require visa sponsorship?"}], self.prefs)

    def test_challenge_detection(self):
        self.assertTrue(looks_like_challenge("Please verify you are human before continuing"))
        self.assertFalse(looks_like_challenge("Application submitted successfully"))


if __name__ == "__main__":
    unittest.main()
