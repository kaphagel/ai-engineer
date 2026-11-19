# IAIEP – Project status and handoff

**Last updated:** 2026-11-19 (Phase 1, hopper template step 1 done)
**Current phase:** Phase 1 – Feasibility prototype (in progress)
**State:** The hopper pipeline runs end to end (input set → FreeCAD worker → model, drawing PDF, STEP, flat-pattern DXF, BOM → checks and report) and is tested against a real reference delivery (ADR-0004). Template step 2 (tier beams and stiffeners) is done; next: step 3 (top panels and support interface). Testing uses the local Ollama model; the Anthropic account still has no credit.

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
| [adr/0004-hopper-template-wall-panels.md](adr/0004-hopper-template-wall-panels.md) | Hopper template from wall panels; comparison with the reference delivery. |
| [../workers/freecad/README.md](../workers/freecad/README.md) | FreeCAD worker: build, run, layout. |
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

### Reference data (received 19 Nov 2026)

Company data is **confidential (D-15)** and lives only in git-ignored folders: `doc/drawings/` (as received) and `data/reference/` (input sets and reference values derived from it). Use it only with local tools and models (Ollama), never with a cloud model.

- **Main reference: a complete issued ESP delivery (2025)** in `doc/drawings/`: all sub-deliveries (casing, hopper, internals, rapping, nozzles, support structure, walkways, penthouse) with delivery lists (PDF/XLSX), CATIA-exported DWG and PDF drawings with text, and 3D exports for some. Not yet received: the folders with customer documents and meeting notes, which are needed for the AI extraction test (F-3).
- Earlier, smaller sets (fabric filter hoppers, an older pyramidal hopper DWG without dimensions) were reviewed and are superseded by the delivery above.

### Phase 1: hopper pipeline and template — steps 1 and 2 done

- **FreeCAD worker** (`workers/freecad/`, ADR-0001 amended): two phases (headless build, then GUI offscreen PDF export). A deadlock of the FreeCAD GUI in offscreen mode was found and fixed (notification area; finding 9), verified with 60 of 60 export runs.
- **Template `esp.hopper` 0.3.0** (ADR-0004): trough or pyramidal hopper from flat wall panels in tiers, with panel gaps, tier beams (channels) and vertical stiffeners (angles) from a profile catalogue in the input set. Outputs: native model, STEP AP242, drawing PDF (sheet and scale chosen automatically, title block, dimensions, parts list, notes, DRAFT marking), one DXF flat pattern per distinct panel, BOM.
- **Platform**: `iaiep.cad.worker` (runs a job in the worker container), `iaiep.checks`, and the ESP domain package `domains/esp` (`iaiep_esp.hopper`: input set with a source per value, independent calculation, checks, reference comparison, command `iaiep-hopper`).
- **Checks** (64 on the reference case): worker drawing checks; model against the independent calculation (panel sizes, slopes, valley angle, capacity, interferences, beam and stiffener set and lengths); design criterion (reported as unapproved while it is a placeholder); BOM plate and profile counts and masses; each DXF read back; PDF text (status marking, main dimensions); native model opens with all parts visible.
- **Reference result**: generated panel plates match the issued part drawings within 0.3–2.5 mm and their masses within 0.2 %, except the middle-tier end panel (+21.8 mm, joint allowance to be explained by the engineering owner). Beam and stiffener counts match; lengths within 1 mm apart from the same plate differences; welded panel net masses within −0.9 % to +0.7 %.

Run:

```bash
docker build --build-arg UID=$(id -u) -t iaiep-freecad-worker:dev workers/freecad
uv run iaiep-hopper domains/esp/examples/hopper_synthetic.toml --out out/hopper-synthetic
uv run iaiep-hopper data/reference/esp-project/hopper_case.toml \
    --reference data/reference/esp-project/hopper_reference.toml --out out/hopper-reference
```

## 3. Next steps

### Phase 1 (developer / coding agent)

1. **Step 3:** top panels and the support interface (column grid, column plates).
2. **Step 4:** bracing, inspection door, level studs; drawing set closer to the reference (sections, details).
3. Document extraction and AI extraction (Ollama) of the hopper input set, once the reference input documents are available (F-3).
4. Store runs, inputs and check results in PostgreSQL with internal versions (spec §25 Phase 1).
5. Repeatability measurement (F-6) and the remaining F-criteria.

Optional, when the Anthropic account has credit: rerun `spikes/llm-tool-calling` against Claude (synthetic data only) and update ADR-0002 and X-02.

### Product owner actions

| # | Action | Spec ref |
|:---|:---|:---|
| 1 | ~~Get a Claude API key~~ Key in `.env` and valid. **Still needed: buy prepaid credit** (Console → Settings → Billing) and set a spend limit | D-16 |
| 2 | Formally appoint the internal engineer as engineering owner | §30.2, D-10 |
| 3 | Agree targets F-1 to F-7 with the engineering owner | §1.2 |
| 4 | ~~Collect reference hopper cases~~ One complete delivery received. **Still needed:** its pre-design input documents (customer specification, design basis, meeting notes), and if possible 1–2 more cases | §1.2 |
| 5 | Record today's manual effort for those cases (before seeing platform results) | §1.2, F-4 |
| 6 | Ask the drafting office: existing CATIA drawing template, title block, numbering, revision scheme? | D-06 to D-08 |
| 7 | Ask IT / document control which PDM/PLM system is used with CATIA | X-05, D-19 |
| 8 | Get company approval of a cloud AI provider for real (confidential) data | D-16 |

## 4. Open questions and notes

- For the engineering owner: stiffener top extensions, bottom clearances and beam end extensions differ per tier in the reference (template inputs, ADR-0004 step 2). Is there a rule behind them? Also: which profile standard (thicknesses, kg/m table) applies, and the steel density (7850 assumed)?
- Drawing: a long general-tolerance text overlaps the scale field in the title block (cosmetic, to fix).
- For the engineering owner: the reference shortens the middle-tier end panel by about 20 mm more than the template's joint rule, and the bottom-tier side panel by about 2.5 mm (ADR-0004). Which joint detail causes this?

- Taiga-S1 (Hugging Face CAD command model) was evaluated and **not adopted**: it drives the FreeCAD GUI step by step for simple PartDesign features and does not fit the template-first approach, drawings or document understanding.
- The laptop GPU (RTX 3500 Ada, 12 GB) was not used; the Ollama server on `ecsserver` is used instead.
- `ecsserver` holds an unsuitable model (`jimscard/adult-film-screenwriter-nsfw`); recommend `ollama rm` if the server is used for company work. The platform must only use explicitly approved models.
