## Context

`skill_loader.py` currently scans only `~/.claude/skills/` top-level for `*-perspective` directories. This ties the service to the user's local machine state. Huashu-nuwa generated skills (feynman, taleb, elon-musk, naval, zhangxuefeng, sun-yuchen) exist only in `huashu-nuwa/examples/` which is NOT scanned.

Goal: make skills self-contained within the project, version-controlled, portable.

## Goals / Non-Goals

**Goals:**
- Project has its own `skills/` directory with all perspective skills
- `skill_loader.py` scans project `skills/` as primary source
- `~/.claude/skills/` kept as secondary source for user-installed skills
- Dedup: project-local wins
- Zero frontend/API changes

**Non-Goals:**
- Don't change how skills are applied to agents
- Don't filter caveman-perspective from dropdown
- Don't modify huashu-nuwa generator

## Decisions

### Decision 1: Project-local `skills/` directory as primary source

**Chosen**: Create `skills/` in project root. Copy all available `*-perspective` skill directories into it. `skill_loader.py` resolves `SKILLS_DIR` relative to `__file__`.

**Alternatives considered**:
- Symlinks: fragile across OS/checkouts. Copy is simpler.
- Only huashu-nuwa examples: incomplete — should also bundle the already-working skills for full portability.

**Rationale**: Self-contained project. Deploy to ECS without worrying about `~/.claude/skills/` state. Version-controlled — skills evolve with the codebase.

### Decision 2: Keep `~/.claude/skills/` as secondary scan path

**Chosen**: After scanning `./skills/`, also scan `~/.claude/skills/`. Skills already found from project-local source are skipped (dedup by name).

**Rationale**: Backward compatible. Users who install custom perspective skills in `~/.claude/skills/` still see them. Project-local versions take precedence for overrides.

### Decision 3: Copy skills from all available sources

**Chosen**: Gather skills from 3 sources into `./skills/`:
1. `~/.claude/skills/*-perspective/` (real dirs and symlinks)
2. `~/.agents/skills/*-perspective/` (symlink targets)
3. `~/.claude/skills/huashu-nuwa/examples/*-perspective/` (examples not yet linked)

**Rationale**: Max coverage. Existing symlinks resolve to `~/.agents/skills/`; read from there directly.

### Decision 4: `SKILLS_DIR` resolution

**Chosen**: `SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills")`

**Rationale**: Works regardless of CWD. Deploy-friendly — resolves relative to `skill_loader.py` location.

## Risks / Trade-offs

- **Copy maintenance**: If huashu-nuwa regenerates a skill, `./skills/` copy becomes stale. Mitigation: `./skills/` is the source of truth for the debate service. Update manually, or add a sync script later.
- **Git repo size**: Each SKILL.md is ~5-30KB. 15 skills ≈ 300KB. Negligible.
- **Duplicate with ~/.claude/skills/**: Some skills already exist both places. Dedup by name handles this.
