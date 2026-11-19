# IAIEP – Project status and handoff

**Last updated:** 2026-11-19 (Phase 0 complete)
**Current phase:** Phase 1 – Feasibility prototype (starting, with synthetic data)
**State:** Phase 0 is complete: spikes done, project tooling and CI in place (ADR-0003). Next: the parametric hopper template with synthetic data. Testing uses the local Ollama model; the Anthropic account still has no credit.

To resume, open this repository in VS Code (Dev Container) and tell the coding agent:

> Read `doc/PROJECT_STATUS.md` and `doc/IAIEP_Comprehensive_Specification_v1.2.md`, then continue from "Next steps".

---

## 1. Key documents

| Document | Purpose |
|:---|:---|
| [IAIEP_Comprehensive_Specification_v1.2.md](IAIEP_Comprehensive_Specification_v1.2.md) | The specification. Single source of architectural intent. |
| [adr/0001-freecad-headless-execution.md](adr/0001-freecad-headless-execution.md) | FreeCAD spike results and decisions. |
| [adr/0002-llm-tool-calling.md](adr/0002-llm-tool-calling.md) | AI tool-calling spike results and decisions. |
| [adr/0003-repository-conventions.md](adr/0003-repository-conventions.md) | Layout, tooling, coding, testing and schema conventions. |
| [archive/IAIEP_Comprehensive_Specification_v1.1.md](archive/IAIEP_Comprehensive_Specification_v1.1.md) | Superseded version, kept for history only. |
| [../spikes/freecad-headless/README.md](../spikes/freecad-headless/README.md) | How to rerun the FreeCAD spike. |

## 2. What was done (sessions of 18–19 Nov 2026)

### Specification review → v1.2

v1.1 was reviewed, and v1.2 written. Main changes (full list in the spec's revision history):

- Converted to GitHub-flavored Markdown (lists and tables were broken in v1.1).
- §1.1 constraints: one developer, internal use, single-tenant, no deadline; the company uses CATIA; cloud AI accepted; internal engineer available.
- §1.2 **prototype objectives F-1 to F-7** with measurable go/no-go criteria (drawing quality, CATIA/process usability, AI extraction accuracy with zero invented values, ≥50 % effort saving, workshop usability, repeatability, cost).
- Phases reordered: Phase 0 foundation → **Phase 1 feasibility prototype (hopper)** → Phase 2 walking skeleton → … → Phase 10 plant engineering.
- New sections: agent execution model (§6.7), template-first CAD (§12.3), CAD tool boundary for CATIA (§12.1), engineering drawings (§12.7), ISO drawing standard profile (§12.8), MVP security profile (§16).
- Rule: AI agent roles are added only when independence, measured improvement or different permissions justify them (§24.2).
- An external review was incorporated (critical vs. non-critical fields for F-3, total effort for F-4, defined repeatability for F-6, PDM, AI vs. human checking, audit tamper protection, GDPR, and more).
- §30 is now a decision register: D-01 to D-25 decided; E-01 to E-05 need the engineering owner or legal advice; X-01 to X-05 are answered by evidence.

### Key decisions (details in spec §30)

- First component: **ESP hopper**, modelled as individual welded plates (ADR-0001).
- CAD: **FreeCAD 1.1.4** (pinned), TechDraw for drawings.
- Formats: **STEP AP242** (3D), **PDF** (issued drawings), **DXF** (geometry, flat patterns). No DWG.
- Drawing standard: **ISO (EN ISO)**, first-angle projection, mm.
- Title block, numbering (`P1234-ESP-HOP-DWG-0001`) and revision codes (A, B, C before release; 0, 1, 2 after): **interim**, until the company's CATIA standards are checked.
- Architecture: modular monolith (Python 3.12) plus a separate FreeCAD worker (FreeCAD bundles its own Python 3.11).
- Storage: PostgreSQL 17 with pgvector; NATS JetStream; SeaweedFS for objects from Phase 6.
- AI: provider-neutral interface (OpenAI-compatible). Primary: approved EU cloud provider. A **personal Claude key may be used for synthetic data only**.
- Until the release gate is enabled, all outputs are marked "DRAFT – NOT FOR FABRICATION".

### Development environment

- `.devcontainer/` contains Python 3.12 + uv, Node LTS, PostgreSQL 17 (`pgvector/pgvector:pg17`) and NATS with JetStream. It was built and tested, and services connect.
- Connection settings inside the container: `DATABASE_URL=postgresql://iaiep:iaiep@postgres:5432/iaiep`, `NATS_URL=nats://nats:4222` (development credentials only).
- `.gitignore` and `.env.example` were created. `.env` (secrets) is git-ignored.
- Git repository on GitHub: `https://github.com/kaphagel/ai-engineer` (private), branch `main`.
- Dev container: loads `.env` if present, sets `LLM_BASE_URL`/`LLM_MODEL` to the Ollama server, and can start other containers (Docker outside of Docker) for the FreeCAD worker.
- Host: WSL2 with Docker; laptop GPU NVIDIA RTX 3500 Ada (12 GB).

### Phase 0 spike 1: FreeCAD headless — done

See ADR-0001. In short:

- Works headless (`freecadcmd`): parametric model, regeneration, geometry check, TechDraw views and dimensions, FCStd, STEP AP242, DXF.
- PDF/SVG drawing export needs the GUI binary with `QT_QPA_PLATFORM=offscreen` (no Xvfb). It must show the page and **wait for the background view computation**, otherwise it silently produces a wrong PDF while reporting success.
- Findings for Phase 1: model the hopper as individual plates; use `optimalBoundingBox()`; automatic drawing checks are essential (views inside the frame, no placeholder text, title block matches metadata); the container needs a non-root user.
- Repeatability: geometry and DXF identical between runs; STEP identical except the header timestamp.

### Phase 0 spike 2: AI tool calling — done (local model)

See ADR-0002. In short:

- Anthropic key is in `.env` and valid, but the account has **no credit** ("credit balance is too low"). Buy prepaid credit to use it.
- Local model server: Ollama on `ecsserver` (192.168.10.41:11434), opened to the LAN. CPU only (Quadro K6000 GPUs too old).
- Model `qwen3:30b-a3b`: 3/3 runs correct; tool called, schema valid, 6.0 m converted to 6000 mm, missing plate thickness flagged and not invented, source quotes genuine. About 4.5 minutes per call.
- Calls go through the OpenAI-compatible interface (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`), so switching to Claude is a configuration change.

### Phase 0: project tooling — done

See ADR-0003. `pyproject.toml` with uv (`uv.lock`), Ruff (lint and format), mypy (strict) and pytest; package `src/iaiep/` with the first module `iaiep.config` (model endpoint settings from environment variables). GitHub Actions CI runs all checks on every push and pull request. The Dev Container runs `uv sync` on creation. Spec §30 stays the decision register (no separate `open-decisions.md`).

### Reference drawings (received 19 Nov 2026)

Company drawings are stored in `doc/drawings/`, which is **git-ignored** (confidential, D-15). Only use them with local models.

- `ESP Hopper/` (5 sheets, DWG, 2012): pyramidal hoppers with stiffener rings, vertical stiffeners and support frame; note "Plate thickness 5 mm". Exported from CATIA as flattened lines: no text objects, no dimensions, sheet scale. Useful as a shape and layout reference only. The title block suggests a fabric filter hopper; to be confirmed.
- Two earlier fabric filter hopper sets (one CATIA PDF with text and delivery lists, one scanned plot PDF) were reviewed and then removed from the folder.
- Missing for Phase 1: the **input documents** (customer specification, design basis) for a reference case, and dimensioned drawings or a STEP export.

## 3. Next steps

### Phase 1 (developer / coding agent), with synthetic data

1. Hopper input schema (Pydantic): dimensions, plate thickness, material, with units and source references. Design criteria (for example minimum valley angle) are labelled placeholders until the engineering owner sets them (E-02).
2. FreeCAD worker container in `workers/freecad/`, based on the spike Dockerfile.
3. Hopper template modelled as individual welded plates (ADR-0001), with geometry checks (valley and wall angles, volume, interface dimensions).
4. Outputs: STEP AP242, drawing PDF marked "DRAFT – NOT FOR FABRICATION" with automatic drawing checks, DXF flat patterns per plate.
5. Command-line pipeline: parameter file in, outputs and check report out.
6. Later: document extraction and AI extraction (Ollama), results stored in PostgreSQL.

Optional, when the Anthropic account has credit: rerun `spikes/llm-tool-calling` against Claude and update ADR-0002 and X-02.

### Product owner actions (needed before Phase 1)

| # | Action | Spec ref |
|:---|:---|:---|
| 1 | ~~Get a Claude API key~~ Key in `.env` and valid. **Still needed: buy prepaid credit** (Console → Settings → Billing) and set a spend limit | D-16 |
| 2 | Formally appoint the internal engineer as engineering owner | §30.2, D-10 |
| 3 | Agree targets F-1 to F-7 with the engineering owner | §1.2 |
| 4 | Collect 2–3 reference hopper cases: pre-design input documents + issued drawings | §1.2 |
| 5 | Record today's manual effort for those cases (before seeing platform results) | §1.2, F-4 |
| 6 | Ask the drafting office: existing CATIA drawing template, title block, numbering, revision scheme? | D-06 to D-08 |
| 7 | Ask IT / document control which PDM/PLM system is used with CATIA | X-05, D-19 |
| 8 | Get company approval of a cloud AI provider for real (confidential) data | D-16 |

## 4. Open questions and notes

- Taiga-S1 (Hugging Face CAD command model) was evaluated and **not adopted**: it drives the FreeCAD GUI step by step for simple PartDesign features and does not fit the template-first approach, drawings or document understanding.
- The laptop GPU (RTX 3500 Ada, 12 GB) was not used; the Ollama server on `ecsserver` is used instead.
- `ecsserver` holds an unsuitable model (`jimscard/adult-film-screenwriter-nsfw`); recommend `ollama rm` if the server is used for company work. The platform must only use explicitly approved models.
