import unittest
from unittest.mock import patch

from ollama_agent.profiles import (
    ResourceError,
    load_profile,
    load_skill,
    profile_names,
    skill_names,
)


class ProfileResourceTests(unittest.TestCase):
    def test_packaged_profiles_load_with_expected_permissions(self):
        self.assertEqual(
            profile_names(),
            (
                "engineer",
                "scope-disciplined-swe",
                "adversarial-pr-reviewer",
            ),
        )
        engineer = load_profile("engineer")
        implementer = load_profile("scope-disciplined-swe")
        reviewer = load_profile("adversarial-pr-reviewer")

        self.assertIn("delegate_agent", engineer.tool_names)
        self.assertNotIn("delegate_agent", implementer.tool_names)
        self.assertNotIn("write_file", reviewer.tool_names)
        self.assertIn("local checkout", reviewer.system_prompt)

    def test_all_and_only_packaged_skills_load_full_instructions(self):
        expected = {
            "systematic-debugging",
            "codebase-architecture-health",
            "technical-evidence-map",
            "safe-merge-conflict-resolution",
            "engineering-handoff",
        }
        self.assertEqual(set(skill_names()), expected)
        for name in expected:
            with self.subTest(name=name):
                skill = load_skill(name)
                self.assertEqual(skill.name, name)
                self.assertGreater(len(skill.instructions), 200)

    def test_unknown_names_fail_clearly(self):
        with self.assertRaisesRegex(ResourceError, "Unknown agent profile 'missing'"):
            load_profile("missing")
        with self.assertRaisesRegex(ResourceError, "Unknown skill 'missing'"):
            load_skill("missing")

    def test_malformed_manifest_fails_clearly(self):
        with patch("ollama_agent.profiles._read_resource", return_value="{"):
            with self.assertRaisesRegex(ResourceError, "Malformed packaged resource"):
                load_profile("engineer")


if __name__ == "__main__":
    unittest.main()
