## Why

Huashu-nuwa generates persona perspective skills (feynman, taleb, elon-musk, naval, zhangxuefeng, sun-yuchen, etc.) but they only exist in `~/.claude/skills/huashu-nuwa/examples/` or `~/.agents/skills/` — not accessible to the debate service in a self-contained way. The project should bundle its own `skills/` directory so all referenced perspective skills are version-controlled, portable, and available regardless of the user's local `~/.claude/skills/` state.

## What Changes

- Create `skills/` directory in project root, populate with all available `*-perspective` skill directories (copied from `~/.claude/skills/`, `~/.agents/skills/`, and `huashu-nuwa/examples/`)
- `skill_loader.py`: Change `SKILLS_DIR` to point to the project's own `skills/` directory (resolved relative to the file's location). Keep `~/.claude/skills/` as a secondary scan path for user-installed skills
- Deduplication: project-local `skills/` wins over user-global `~/.claude/skills/`
- No frontend changes — existing `loadSkills()` already populates all 9 dropdowns from `/api/skills`

## Capabilities

### New Capabilities

- `skill-discovery`: Skill loader discovers perspective skills from the project's own `skills/` directory as the primary source, with `~/.claude/skills/` as a secondary fallback. Deduplication prefers project-local versions.

### Modified Capabilities

<!-- None — no existing spec requirements change -->

## Impact

- **Code**: `skill_loader.py` — change `SKILLS_DIR` to project-relative path, add secondary scan path
- **New directory**: `skills/` at project root with `*-perspective/` subdirectories
- **API**: No breaking changes — `/api/skills` response format unchanged, just returns more skills
- **Frontend**: Zero changes
- **Dependencies**: None new
