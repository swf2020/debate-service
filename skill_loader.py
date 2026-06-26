"""
Load huashu-nuwa distilled persona skills and inject them into agent backstories.

Skills are SKILL.md files stored in:
- Project-local ``skills/{name}-perspective/SKILL.md`` (primary)
- User-global ``~/.claude/skills/{name}-perspective/SKILL.md`` (fallback)
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")
SKILLS_DIR = os.path.expanduser("~/.claude/skills")


def _scan_dir(skills_dir: str) -> list[dict]:
    """Scan a single directory for *-perspective/ subdirectories with SKILL.md.

    Returns a list of dicts with name, path, description.
    """
    skills: list[dict] = []
    if not os.path.isdir(skills_dir):
        return skills

    for entry in sorted(os.listdir(skills_dir)):
        if not entry.endswith("-perspective"):
            continue
        skill_dir = os.path.join(skills_dir, entry)
        if not os.path.isdir(skill_dir):
            continue
        skill_md = os.path.join(skill_dir, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue

        # Try to extract description from the file
        description = ""
        try:
            with open(skill_md, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Skip frontmatter
                    if line == "---":
                        continue
                    # Skip metadata fields
                    if line.startswith("name:") or line.startswith("description:"):
                        if line.startswith("description:"):
                            description = line.replace("description:", "").strip()
                        continue
                    # First non-metadata, non-empty line
                    if line and not description:
                        description = line.lstrip("#").strip()
                        break
        except Exception:
            pass

        skills.append(
            {
                "name": entry,
                "path": skill_md,
                "description": description or entry,
            }
        )

    return skills


def list_available_skills() -> list[dict]:
    """Scan for *-perspective/ skill directories.

    Scans project-local ``skills/`` directory first, then user-global
    ``~/.claude/skills/`` as fallback.  Duplicates are resolved in favour
    of the project-local version.

    Returns a list of dicts like::

        [
            {"name": "munger-perspective", "path": "/Users/.../SKILL.md",
             "description": "..."},
            ...
        ]
    """
    seen: dict[str, dict] = {}

    # 1. Project-local skills (primary)
    for skill in _scan_dir(PROJECT_SKILLS_DIR):
        seen[skill["name"]] = skill

    # 2. User-global skills (fallback — only if not already seen)
    for skill in _scan_dir(SKILLS_DIR):
        if skill["name"] not in seen:
            seen[skill["name"]] = skill

    # Return sorted by name
    return [seen[k] for k in sorted(seen)]


def load_perspective_skill(skill_name: str | None) -> str | None:
    """Load the SKILL.md content for a given skill name.

    Tries project-local ``skills/`` directory first, then user-global
    ``~/.claude/skills/`` as fallback.

    Args:
        skill_name: e.g., ``"munger-perspective"`` or ``None``.

    Returns:
        Full content of SKILL.md as a string, or ``None`` if the skill
        doesn't exist or *skill_name* is ``None``.
    """
    if not skill_name:
        return None

    # Normalize: strip path separators
    skill_name = os.path.basename(skill_name)

    # Try project-local first, then user-global
    for base_dir in (PROJECT_SKILLS_DIR, SKILLS_DIR):
        skill_path = os.path.join(base_dir, skill_name, "SKILL.md")
        if os.path.isfile(skill_path):
            try:
                with open(skill_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return None

    return None


def build_backstory_with_skill(base_backstory: str, skill_name: str | None) -> str:
    """Append skill content to a base backstory.

    Args:
        base_backstory: The default backstory text for the agent.
        skill_name: The skill to load, or ``None`` to use the base backstory
            as-is.

    Returns:
        Combined backstory string.  If skill is loaded, appends::

            "\\n\\n## 你的思维框架（来自 {skill_name}）\\n\\n{skill_content}"
    """
    if not skill_name:
        return base_backstory

    skill_content = load_perspective_skill(skill_name)
    if not skill_content:
        return base_backstory

    return f"{base_backstory}\n\n## 你的思维框架（来自 {skill_name}）\n\n{skill_content}"
