import unittest

from src.platforms.internshala import build_internshala_url, role_to_slug


class InternshalaMappingTests(unittest.TestCase):
    def test_known_role(self):
        self.assertEqual(role_to_slug("Software Development"), "software-development")

    def test_role_alias(self):
        self.assertEqual(role_to_slug("software developer"), "software-development")

    def test_unknown_role_is_slugified(self):
        self.assertEqual(role_to_slug("Quantum Research Intern"), "quantum-research-intern")

    def test_empty_role_has_safe_default(self):
        self.assertEqual(role_to_slug(""), "software-development")

    def test_job_url(self):
        self.assertEqual(
            build_internshala_url("data-science", "job"),
            "https://internshala.com/jobs/data-science-jobs",
        )

    def test_internship_url(self):
        self.assertEqual(
            build_internshala_url("data-science", "internship"),
            "https://internshala.com/internships/data-science-internship",
        )


if __name__ == "__main__":
    unittest.main()
