# IAIEP – Industrial AI Engineering Platform

AI-assisted engineering platform for industrial equipment, starting with electrostatic precipitators (ESP).

- **Current status and next steps:** [doc/PROJECT_STATUS.md](doc/PROJECT_STATUS.md)
- **Specification:** [doc/IAIEP_Comprehensive_Specification_v1.2.md](doc/IAIEP_Comprehensive_Specification_v1.2.md)
- **Architecture decisions:** [doc/adr/](doc/adr/)

Development environment: open the folder in VS Code and choose **Dev Containers: Reopen in Container**. Then:

```bash
uv sync                  # install dependencies (done automatically on container creation)
uv run ruff check        # lint
uv run ruff format       # format
uv run mypy              # type check
uv run pytest            # tests
```

Hopper pipeline (Phase 1), with synthetic example data:

```bash
docker build --build-arg UID=$(id -u) -t iaiep-freecad-worker:dev workers/freecad
uv run iaiep-hopper domains/esp/examples/hopper_synthetic.toml --out out/hopper-synthetic
```

Conventions: [doc/adr/0003-repository-conventions.md](doc/adr/0003-repository-conventions.md). Company reference data is confidential and lives only in the git-ignored `doc/drawings/` and `data/reference/` folders.
