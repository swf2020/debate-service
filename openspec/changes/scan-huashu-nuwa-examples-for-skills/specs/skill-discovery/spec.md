## ADDED Requirements

### Requirement: Skill loader scans project skills directory as primary source

The skill loader SHALL scan the project's own `skills/` directory (resolved relative to `skill_loader.py`) for `*-perspective` skill directories containing a `SKILL.md` file.

#### Scenario: Project skills directory exists with perspective skills

- **WHEN** `skills/` directory exists at project root and contains subdirectories ending in `-perspective` with `SKILL.md` files
- **THEN** `list_available_skills()` returns those skills

#### Scenario: Project skills directory does not exist

- **WHEN** `skills/` directory does not exist at project root
- **THEN** `list_available_skills()` returns an empty list (no error)

### Requirement: Skill loader falls back to user skills directory

The skill loader SHALL also scan `~/.claude/skills/` for `*-perspective` skills as a secondary source, adding skills not already found in the project `skills/` directory.

#### Scenario: User skills directory has additional skills

- **WHEN** `~/.claude/skills/` contains a `*-perspective` skill not present in project `skills/`
- **THEN** that skill appears in the result alongside project skills

#### Scenario: User skills directory does not exist

- **WHEN** `~/.claude/skills/` does not exist
- **THEN** `list_available_skills()` returns only project skills without error

### Requirement: Deduplication prefers project-local skills

When the same skill name exists in both project `skills/` and `~/.claude/skills/`, the skill loader SHALL use the project-local version and skip the user-global copy.

#### Scenario: Skill exists in both locations

- **WHEN** `munger-perspective` exists in both project `skills/munger-perspective/` and `~/.claude/skills/munger-perspective/`
- **THEN** `list_available_skills()` includes exactly one entry for `munger-perspective` with `path` pointing to the project-local version

### Requirement: load_perspective_skill resolves from both directories

`load_perspective_skill(skill_name)` SHALL attempt to load from project `skills/{name}/SKILL.md` first, then fall back to `~/.claude/skills/{name}/SKILL.md`.

#### Scenario: Skill only in project directory

- **WHEN** skill exists only in project `skills/` and not in `~/.claude/skills/`
- **THEN** `load_perspective_skill("feynman-perspective")` returns the content from project `skills/`

#### Scenario: Skill exists in both, project version loaded

- **WHEN** skill exists in both project `skills/` and `~/.claude/skills/`
- **THEN** `load_perspective_skill(name)` returns content from the project-local version

#### Scenario: Skill does not exist in either location

- **WHEN** skill name does not match any directory in either scan location
- **THEN** `load_perspective_skill(name)` returns `None`

### Requirement: API response format unchanged

The `GET /api/skills` endpoint SHALL continue to return `{"skills": [{"name", "path", "description"}, ...]}` with the same field structure.

#### Scenario: API returns skill list from both sources

- **WHEN** client calls `GET /api/skills`
- **THEN** response includes all skills from project `skills/` and unique skills from `~/.claude/skills/` in the same `{"skills": [...]}` format
