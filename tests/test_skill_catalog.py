import unittest

from orchestrator.skill_catalog import (
    ADHD_SKILL_LICENSE,
    ADHD_SKILL_NAME,
    ADHD_SKILL_SOURCE,
    SKILL_GUARDRAILS,
    default_adhd_instruction,
    enrich_skill_prompt,
)


class SkillCatalogTests(unittest.TestCase):
    def test_builtin_skill_is_enabled_by_default_and_can_be_disabled(self) -> None:
        enabled = default_adhd_instruction()
        self.assertIn(ADHD_SKILL_NAME, enabled)
        self.assertIn(ADHD_SKILL_SOURCE, enabled)
        self.assertIn(ADHD_SKILL_LICENSE, enabled)
        self.assertEqual(default_adhd_instruction(False), "")

    def test_every_role_skill_has_a_guardrail_and_is_idempotent(self) -> None:
        self.assertEqual(len(SKILL_GUARDRAILS), 20)
        enriched = enrich_skill_prompt("Web Research", "Use primary sources.")
        self.assertIn("Orbit operating contract", enriched)
        self.assertEqual(enrich_skill_prompt("Web Research", enriched), enriched)


if __name__ == "__main__":
    unittest.main()
