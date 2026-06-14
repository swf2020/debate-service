"""
Load huashu-nuwa distilled persona skills and inject them into agent backstories.

Skills are SKILL.md files stored in ``~/.claude/skills/{name}-perspective/SKILL.md``.
"""

from __future__ import annotations

import os
from pathlib import Path

SKILLS_DIR = os.path.expanduser("~/.claude/skills")


def list_available_skills() -> list[dict]:
    """Scan SKILLS_DIR for *-perspective/ directories containing SKILL.md.

    Returns a list of dicts like::

        [
            {"name": "munger-perspective", "path": "/Users/.../SKILL.md",
             "description": "..."},
            ...
        ]

    The description is extracted from the SKILL.md frontmatter or first
    meaningful line.
    """
    skills: list[dict] = []
    if not os.path.isdir(SKILLS_DIR):
        return skills

    for entry in sorted(os.listdir(SKILLS_DIR)):
        if not entry.endswith("-perspective"):
            continue
        skill_dir = os.path.join(SKILLS_DIR, entry)
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


def load_perspective_skill(skill_name: str | None) -> str | None:
    """Load the SKILL.md content for a given skill name.

    Args:
        skill_name: e.g., ``"munger-perspective"`` or ``None``.

    Returns:
        Full content of SKILL.md as a string, or ``None`` if the skill
        doesn't exist or *skill_name* is ``None``.
    """
    if not skill_name:
        return None

    # Normalize: strip path separators, ensure ends with -perspective
    skill_name = os.path.basename(skill_name)
    skill_path = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")

    if not os.path.isfile(skill_path):
        return None

    try:
        with open(skill_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
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
