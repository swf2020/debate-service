## 1. Populate project skills directory

- [x] 1.1 Create `skills/` directory at project root
- [x] 1.2 Copy all `*-perspective` skills from `~/.claude/skills/` into `skills/` (resolve symlinks to `~/.agents/skills/`)
- [x] 1.3 Copy all `*-perspective` skills from `~/.claude/skills/huashu-nuwa/examples/` not already present into `skills/`

## 2. Tests

- [x] 2.1 Write test: `list_available_skills()` returns skills from project `skills/` directory
- [x] 2.2 Write test: skills from `~/.claude/skills/` included when not in project `skills/`
- [x] 2.3 Write test: dedup — project-local skill wins when same name exists in both dirs
- [x] 2.4 Write test: graceful fallback when project `skills/` dir is empty or missing
- [x] 2.5 Write test: `load_perspective_skill()` loads from project `skills/` first, then `~/.claude/skills/`
- [x] 2.6 Write test: `load_perspective_skill()` returns `None` for non-existent skill

## 3. Implementation

- [x] 3.1 Add `PROJECT_SKILLS_DIR` constant resolved relative to `__file__` in `skill_loader.py`
- [x] 3.2 Extract `_scan_dir(skills_dir)` helper to avoid code duplication
- [x] 3.3 Update `list_available_skills()`: scan `PROJECT_SKILLS_DIR` first, then `~/.claude/skills/` (if exists), dedup by name (project-local wins)
- [x] 3.4 Update `load_perspective_skill()`: try `PROJECT_SKILLS_DIR/{name}/SKILL.md` first, then `~/.claude/skills/{name}/SKILL.md`

## 4. Verification

- [x] 4.1 Run `pytest test_skill_loader.py -v` — all tests pass (28/28)
- [x] 4.2 Run `python -c "from skill_loader import list_available_skills; print(len(list_available_skills()))"` — 15 skills returned
- [x] 4.3 Run broader test suite (`test_debate_flow.py`, `test_agents.py`) — all 107 tests pass, no regressions
