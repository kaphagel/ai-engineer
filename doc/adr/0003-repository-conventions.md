# ADR-0003: Repository, coding and testing conventions

- **Status:** Accepted
- **Date:** 2026-11-19
- **Related:** spec §21, §25 (Phase 0), §27, §28, D-12, D-13, D-23

## Context

Phase 0 requires coding standards, a testing strategy, CI, and conventions for versioned APIs and data schemas before Phase 1 code is written.

## Decision

**Layout** (spec §28, created only when needed):

- `src/iaiep/`: the platform, one Python 3.12 package (modular monolith).
- `workers/freecad/`: the CAD worker, which runs inside FreeCAD's own Python 3.11 and never imports `iaiep`.
- `domains/<domain>/`: equipment-domain packages.
- `tests/unit`, `tests/integration`, `tests/e2e`, `tests/evaluation`.
- `spikes/`: throw-away Phase 0 code. Excluded from linting and type checking.

**Tooling.** All configuration is in `pyproject.toml`; dependencies are locked in `uv.lock`.

| Purpose | Tool | Command |
|:---|:---|:---|
| Dependencies | uv | `uv sync` |
| Lint | Ruff | `uv run ruff check` |
| Format | Ruff | `uv run ruff format` |
| Type check | mypy (strict) | `uv run mypy` |
| Tests | pytest | `uv run pytest` |

GitHub Actions (`.github/workflows/ci.yml`) runs all of these on every push to `main` and on every pull request. mypy was chosen as the type checker of record; Pylance in VS Code is used for editing only.

**Coding rules** (spec §27.2): typed code, inputs and outputs validated with typed schemas, no hard-coded secrets, endpoints, models or paths (configuration from environment variables, see `iaiep.config`), and tests with every feature.

**Testing strategy** (spec §21):

- Unit tests: fast, no network, no database, no FreeCAD. Always run in CI.
- Integration tests: PostgreSQL, NATS or the FreeCAD worker container. Run in the Dev Container; added to CI when they exist.
- Evaluation tests: model behaviour (for example AI extraction against reference inputs). Slow (local model about 5 min per call) and run on demand, never in CI.
- Confidential reference data (D-15) is never committed and never used in CI. Only synthetic data is committed.

**Data-schema and API conventions:**

- Schemas are Pydantic models. Exchanged schemas (messages, artifacts, API bodies) carry an explicit `schema_version` and are exported to JSON Schema in the repository (D-12).
- Engineering quantities are stored in SI-based units stated in the field name or schema (for example `height_mm`), per §10.5.
- HTTP APIs are versioned in the path (`/api/v1/...`). Breaking changes require a new version.
- IDs are UUIDv7; database migrations use Alembic, linear and forward-only (D-13).

**Deployment target:** Docker Compose on a single host (D-23).

**Decision register:** spec §30 remains the register of decisions. No separate `doc/open-decisions.md` is kept; ADRs record the details.

## Consequences

- New modules must pass Ruff and strict mypy from the start.
- FreeCAD worker code has its own checks, because it runs on a different Python version. These are defined when the worker is created in Phase 1.
