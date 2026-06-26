"""Tests for debate_service.skill_loader."""

import os
import tempfile
import unittest
from unittest.mock import patch

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


class TestProjectSkillsDir(unittest.TestCase):
    """Tests for project-local skills/ directory scanning."""

    def _make_skill(self, skills_dir, name, description="Test skill"):
        """Create a minimal perspective skill directory with SKILL.md."""
        skill_dir = os.path.join(skills_dir, name)
        os.makedirs(skill_dir, exist_ok=True)
        skill_md = os.path.join(skill_dir, "SKILL.md")
        with open(skill_md, "w", encoding="utf-8") as f:
            f.write(f"---\ndescription: {description}\n---\n# {name}\n\nTest content.")
        return skill_md

    def test_returns_skills_from_project_dir(self):
        """list_available_skills() returns skills from project skills/ dir."""
        with tempfile.TemporaryDirectory() as proj_dir, \
             tempfile.TemporaryDirectory() as user_dir:
            self._make_skill(proj_dir, "test-hero-perspective", "A test hero")
            # User dir empty
            with _patch_skills_dirs(proj_dir, user_dir):
                skills = list_available_skills()
                names = [s["name"] for s in skills]
                self.assertIn("test-hero-perspective", names)
                self.assertEqual(len(skills), 1)

    def test_returns_skills_from_user_dir(self):
        """Skills only in user dir are also returned."""
        with tempfile.TemporaryDirectory() as proj_dir, \
             tempfile.TemporaryDirectory() as user_dir:
            self._make_skill(user_dir, "user-only-perspective", "User skill")
            with _patch_skills_dirs(proj_dir, user_dir):
                skills = list_available_skills()
                names = [s["name"] for s in skills]
                self.assertIn("user-only-perspective", names)
                self.assertEqual(len(skills), 1)

    def test_merges_both_dirs(self):
        """Skills from both project and user dirs appear together."""
        with tempfile.TemporaryDirectory() as proj_dir, \
             tempfile.TemporaryDirectory() as user_dir:
            self._make_skill(proj_dir, "proj-skill-perspective", "Project")
            self._make_skill(user_dir, "user-skill-perspective", "User")
            with _patch_skills_dirs(proj_dir, user_dir):
                skills = list_available_skills()
                names = [s["name"] for s in skills]
                self.assertIn("proj-skill-perspective", names)
                self.assertIn("user-skill-perspective", names)
                self.assertEqual(len(skills), 2)

    def test_dedup_project_wins(self):
        """When same skill exists in both, project version wins (appears once)."""
        with tempfile.TemporaryDirectory() as proj_dir, \
             tempfile.TemporaryDirectory() as user_dir:
            self._make_skill(proj_dir, "shared-perspective", "PROJECT version")
            self._make_skill(user_dir, "shared-perspective", "user version")
            with _patch_skills_dirs(proj_dir, user_dir):
                skills = list_available_skills()
                names = [s["name"] for s in skills]
                self.assertEqual(names.count("shared-perspective"), 1)
                # Project version wins — path should be from proj_dir
                skill = [s for s in skills if s["name"] == "shared-perspective"][0]
                self.assertIn(proj_dir, skill["path"])

    def test_project_dir_missing_graceful(self):
        """When project skills/ doesn't exist, still returns user skills."""
        with tempfile.TemporaryDirectory() as user_dir:
            self._make_skill(user_dir, "fallback-perspective", "Fallback")
            nonexistent = "/tmp/__nonexistent_proj_skills__"
            with _patch_skills_dirs(nonexistent, user_dir):
                skills = list_available_skills()
                names = [s["name"] for s in skills]
                self.assertIn("fallback-perspective", names)
                self.assertEqual(len(skills), 1)

    def test_both_dirs_missing_returns_empty(self):
        """When neither dir exists, returns empty list without error."""
        with _patch_skills_dirs("/tmp/__no_proj__", "/tmp/__no_user__"):
            self.assertEqual(list_available_skills(), [])

    def test_sorted_result_from_both_dirs(self):
        """Combined results are sorted alphabetically."""
        with tempfile.TemporaryDirectory() as proj_dir, \
             tempfile.TemporaryDirectory() as user_dir:
            self._make_skill(proj_dir, "zebra-perspective", "Z")
            self._make_skill(user_dir, "alpha-perspective", "A")
            with _patch_skills_dirs(proj_dir, user_dir):
                skills = list_available_skills()
                names = [s["name"] for s in skills]
                self.assertEqual(names, sorted(names))


class TestLoadPerspectiveSkillDualDir(unittest.TestCase):
    """Tests for load_perspective_skill() with dual directory support."""

    def _make_skill(self, skills_dir, name, content="Test skill content."):
        """Create a minimal perspective skill directory with SKILL.md."""
        skill_dir = os.path.join(skills_dir, name)
        os.makedirs(skill_dir, exist_ok=True)
        skill_md = os.path.join(skill_dir, "SKILL.md")
        with open(skill_md, "w", encoding="utf-8") as f:
            f.write(f"---\ndescription: test\n---\n# {name}\n\n{content}")
        return skill_md

    def test_loads_from_project_dir(self):
        """load_perspective_skill loads from project skills/ dir."""
        with tempfile.TemporaryDirectory() as proj_dir, \
             tempfile.TemporaryDirectory() as user_dir:
            self._make_skill(proj_dir, "test-perspective", "PROJECT CONTENT")
            with _patch_skills_dirs(proj_dir, user_dir):
                content = load_perspective_skill("test-perspective")
                self.assertIsNotNone(content)
                self.assertIn("PROJECT CONTENT", content)

    def test_loads_from_user_dir_fallback(self):
        """When skill not in project dir, loads from user dir."""
        with tempfile.TemporaryDirectory() as proj_dir, \
             tempfile.TemporaryDirectory() as user_dir:
            self._make_skill(user_dir, "user-only-perspective", "USER CONTENT")
            with _patch_skills_dirs(proj_dir, user_dir):
                content = load_perspective_skill("user-only-perspective")
                self.assertIsNotNone(content)
                self.assertIn("USER CONTENT", content)

    def test_project_wins_when_both_exist(self):
        """When skill exists in both dirs, project version is loaded."""
        with tempfile.TemporaryDirectory() as proj_dir, \
             tempfile.TemporaryDirectory() as user_dir:
            self._make_skill(proj_dir, "dual-perspective", "PROJECT WINNER")
            self._make_skill(user_dir, "dual-perspective", "user loser")
            with _patch_skills_dirs(proj_dir, user_dir):
                content = load_perspective_skill("dual-perspective")
                self.assertIn("PROJECT WINNER", content)
                self.assertNotIn("user loser", content)

    def test_returns_none_for_nonexistent(self):
        """Returns None when skill doesn't exist in either dir."""
        with tempfile.TemporaryDirectory() as proj_dir, \
             tempfile.TemporaryDirectory() as user_dir:
            with _patch_skills_dirs(proj_dir, user_dir):
                self.assertIsNone(load_perspective_skill("no-such-perspective"))

    def test_path_normalization_still_works(self):
        """Path normalization works with dual dir setup."""
        with tempfile.TemporaryDirectory() as proj_dir, \
             tempfile.TemporaryDirectory() as user_dir:
            self._make_skill(proj_dir, "normie-perspective", "NORMALIZED")
            with _patch_skills_dirs(proj_dir, user_dir):
                c1 = load_perspective_skill("normie-perspective")
                c2 = load_perspective_skill("/some/path/normie-perspective")
                self.assertEqual(c1, c2)
                self.assertIsNotNone(c1)


# ── Helpers ──────────────────────────────────────────────────────────────────


class _patch_skills_dirs:
    """Context manager that temporarily replaces both PROJECT_SKILLS_DIR and SKILLS_DIR."""

    def __init__(self, project_dir: str, user_dir: str):
        self._proj = project_dir
        self._user = user_dir
        self._orig_proj: str = ""
        self._orig_user: str = ""

    def __enter__(self) -> None:
        import skill_loader as m

        self._orig_proj = getattr(m, "PROJECT_SKILLS_DIR", m.SKILLS_DIR)
        self._orig_user = m.SKILLS_DIR
        m.PROJECT_SKILLS_DIR = self._proj
        m.SKILLS_DIR = self._user

    def __exit__(self, *args: object) -> None:
        import skill_loader as m

        m.PROJECT_SKILLS_DIR = self._orig_proj
        m.SKILLS_DIR = self._orig_user


class _patch_skills_dir:
    """Context manager that temporarily replaces both PROJECT_SKILLS_DIR and SKILLS_DIR."""

    def __init__(self, tmp_dir: str):
        self._tmp = tmp_dir
        self._orig_proj: str = ""
        self._orig_user: str = ""

    def __enter__(self) -> None:
        import skill_loader as m

        self._orig_proj = getattr(m, "PROJECT_SKILLS_DIR", m.SKILLS_DIR)
        self._orig_user = m.SKILLS_DIR
        m.PROJECT_SKILLS_DIR = self._tmp
        m.SKILLS_DIR = self._tmp

    def __exit__(self, *args: object) -> None:
        import skill_loader as m

        m.PROJECT_SKILLS_DIR = self._orig_proj
        m.SKILLS_DIR = self._orig_user


if __name__ == "__main__":
    unittest.main()
