"""Tests for debate_service.skill_loader."""

import os
import tempfile
import unittest

from skill_loader import (
    SKILLS_DIR,
    build_backstory_with_skill,
    list_available_skills,
    load_perspective_skill,
)


class TestListAvailableSkills(unittest.TestCase):
    """Tests for list_available_skills()"""

    def test_returns_list(self):
        """Always returns a list (possibly empty)."""
        result = list_available_skills()
        self.assertIsInstance(result, list)

    def test_each_entry_is_dict(self):
        """Every element is a dict with name, path, description."""
        for entry in list_available_skills():
            self.assertIsInstance(entry, dict)
            self.assertIn("name", entry)
            self.assertIn("path", entry)
            self.assertIn("description", entry)
            self.assertTrue(entry["name"].endswith("-perspective"))
            self.assertTrue(os.path.isfile(entry["path"]))

    def test_sorted_by_name(self):
        """Entries are sorted alphabetically by name."""
        skills = list_available_skills()
        names = [s["name"] for s in skills]
        self.assertEqual(names, sorted(names))

    def test_returns_empty_when_dir_missing(self):
        """When SKILLS_DIR does not exist, return empty list."""
        with _patch_skills_dir("/tmp/__nonexistent_skills_dir__"):
            self.assertEqual(list_available_skills(), [])


class TestLoadPerspectiveSkill(unittest.TestCase):
    """Tests for load_perspective_skill()"""

    def test_none_returns_none(self):
        """None input returns None."""
        self.assertIsNone(load_perspective_skill(None))

    def test_empty_string_returns_none(self):
        """Empty string input returns None."""
        self.assertIsNone(load_perspective_skill(""))

    def test_nonexistent_returns_none(self):
        """A skill that doesn't exist returns None."""
        self.assertIsNone(load_perspective_skill("completely-made-up-perspective"))

    def test_returns_content_for_real_skill(self):
        """If a real *-perspective skill exists, load its content."""
        skills = list_available_skills()
        if not skills:
            self.skipTest("No real perspective skills found on this machine")
        content = load_perspective_skill(skills[0]["name"])
        self.assertIsNotNone(content)
        self.assertIsInstance(content, str)
        self.assertGreater(len(content), 0)

    def test_path_normalization_with_abs_path(self):
        """Passing '/some/path/munger-perspective' still finds the skill."""
        skills = list_available_skills()
        if not skills:
            self.skipTest("No real perspective skills found on this machine")

        real_name = skills[0]["name"]
        content_normal = load_perspective_skill(real_name)
        content_path = load_perspective_skill(f"/some/arbitrary/path/{real_name}")
        self.assertEqual(content_normal, content_path)

    def test_path_normalization_with_rel_path(self):
        """Passing 'foo/bar/skill-perspective' still finds the skill."""
        skills = list_available_skills()
        if not skills:
            self.skipTest("No real perspective skills found on this machine")

        real_name = skills[0]["name"]
        content_normal = load_perspective_skill(real_name)
        content_path = load_perspective_skill(f"some/deep/dir/{real_name}")
        self.assertEqual(content_normal, content_path)


class TestBuildBackstoryWithSkill(unittest.TestCase):
    """Tests for build_backstory_with_skill()"""

    BASE = "你是热衷于辩论的 AI 助手。"

    def test_none_skill_returns_base(self):
        """Without a skill name, the base backstory is returned as-is."""
        result = build_backstory_with_skill(self.BASE, None)
        self.assertEqual(result, self.BASE)

    def test_nonexistent_skill_returns_base(self):
        """With a nonexistent skill, the base backstory is returned as-is."""
        result = build_backstory_with_skill(self.BASE, "no-such-perspective")
        self.assertEqual(result, self.BASE)

    def test_empty_string_returns_base(self):
        """Empty string skill name returns base unchanged."""
        result = build_backstory_with_skill(self.BASE, "")
        self.assertEqual(result, self.BASE)

    def test_appends_skill_content(self):
        """A valid skill appends its content after a heading."""
        skills = list_available_skills()
        if not skills:
            self.skipTest("No real perspective skills found on this machine")

        skill_name = skills[0]["name"]
        result = build_backstory_with_skill(self.BASE, skill_name)

        self.assertIn(self.BASE, result)
        self.assertIn(f"## 你的思维框架（来自 {skill_name}）", result)
        self.assertGreater(len(result), len(self.BASE))

    def test_munger_perspective_appends_correctly(self):
        """Specifically test with munger-perspective if it exists."""
        content = load_perspective_skill("munger-perspective")
        if not content:
            self.skipTest("munger-perspective not available on this machine")

        result = build_backstory_with_skill(self.BASE, "munger-perspective")
        self.assertIn("查理·芒格", result)
        self.assertIn("## 你的思维框架（来自 munger-perspective）", result)

    def test_preserves_heading_format(self):
        """Verify the exact heading format in the appended content."""
        skills = list_available_skills()
        if not skills:
            self.skipTest("No real perspective skills found on this machine")

        result = build_backstory_with_skill(self.BASE, skills[0]["name"])
        expected_heading = f"## 你的思维框架（来自 {skills[0]['name']}）"
        self.assertIn(expected_heading, result)


# ── Helpers ──────────────────────────────────────────────────────────────────


class _patch_skills_dir:
    """Context manager that temporarily replaces SKILLS_DIR."""

    def __init__(self, tmp_dir: str):
        self._tmp = tmp_dir
        self._orig: str = ""

    def __enter__(self) -> None:
        import skill_loader as m

        self._orig = m.SKILLS_DIR
        m.SKILLS_DIR = self._tmp

    def __exit__(self, *args: object) -> None:
        import skill_loader as m

        m.SKILLS_DIR = self._orig


if __name__ == "__main__":
    unittest.main()
