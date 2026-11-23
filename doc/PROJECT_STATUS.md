# IAIEP – Project status and handoff

**Last updated:** 2026-11-23 (session paused; spec v3.0 reviewed and adopted, skill layer drafted, ADR-0005 accepted, TSD analysed)
**Current phase:** Phase 1 – Feasibility prototype (in progress)
**State:** The hopper pipeline runs end to end (input set → FreeCAD worker → model, drawing PDF, STEP, flat-pattern DXF, BOM → checks and report) and is tested against a real reference delivery (ADR-0004): template `esp.hopper` 0.6.0, steps 1–5 done, 77 checks pass, 12-variant sweep passes. On 23 Nov no production code changed: the session reviewed spec v3.0 (AI skills), drafted the first two platform skills, decided how CAD construction continues (ADR-0005) and analysed the company TSD (technical specification document) as the future input for a whole ESP. Testing uses the local Ollama model; the Anthropic account still has no credit.

To resume, open this repository in VS Code (Dev Container) and tell the coding agent:

> Read `doc/PROJECT_STATUS.md` and `doc/IAIEP_Comprehensive_Specification_v3.0.md`, then continue from "Where we left off".

## Where we left off (session 2026-11-23)

**Paused after:** the TSD analysis. Nothing is half-done in code. Commit `3c529f5` (spec v3.0) is pushed; the rest of the session's work is **not committed yet** (see below).

### Uncommitted work (commit first when resuming)

| Path | Content |
|:---|:---|
| `doc/IAIEP_Comprehensive_Specification_v3.0.md` | Edits after commit `3c529f5`: ADR-0005 wording in §3.5/§12.1, planned skill catalogue, phase-plan changes |
| `doc/PROJECT_STATUS.md` | This file |
| `doc/adr/0001-freecad-headless-execution.md` | Notes 13–16 from the freecad-ai review |
| `doc/adr/0005-weldment-operations-and-editable-model.md` | New, accepted |
| `skills/engineering/requirement-analysis/`, `skills/esp/hopper-design/` | Draft platform skills 0.1.0 |
| `.github/skills/freecad-worker/SKILL.md` | Coding-assistant skill: FreeCAD worker rules and commands |
| `spikes/freecad-varset/` | VarSet/expression spike (evidence for ADR-0005) |
| `.gitignore` | Adds `doc/spec/` |

Before committing: scan the staged diff for customer names, project names and real values (D-15). On 23 Nov two confidential TSD spreadsheets were removed from the then-unpushed commits before anything was pushed; GitHub never received them. Never use `git push --mirror` (old local agent checkpoints under `refs/agents/` still contain them).

### What was decided on 23 Nov

- **Spec v3.0 adopted** with review edits: skill naming compatible with the public Agent Skills format, deterministic skill selection for controlled work, refusal instead of reduced permissions, canonical package hash and CI immutability check, version rules, solo-approval rule, confidential evaluation cases in `data/evaluation/`, minimal skill registry moved into the Phase 2 walking skeleton, go/no-go ADR as Phase 1 exit, planned skill catalogue (§6.8.8).
- **Skill granularity:** one skill per type of task, at most one design skill per component family, parts are data, never skills. Platform skills live in `skills/<namespace>/<name>/`; coding-assistant skills in `.github/skills/`.
- **ADR-0005 accepted:** the hopper template becomes a plan generator in the ESP domain package; a generic worker executes plans of general weldment operations (`plate`, `profile`, `tube`, `cut`, `group`); the native FCStd file is a regenerated, inspectable output (spec §3.5, §12.1). Scripted FreeCAD features are not used in files given to users.
- **External projects reviewed:** ghbalf/freecad-ai (LGPL; ideas recorded in ADR-0001 notes 13–16, no code copied) and glotoff/freecad-skills (MIT; nothing useful, not adopted).

### TSD analysis (company technical specification document)

The TSD is the company's one-stop input document for a whole ESP, filled in by the project manager from customer documents before design. Two sanitized examples are in `doc/spec/` (git-ignored, internal; the originals are in `data/reference/tsd/`). Do not commit them or copy their values into committed files.

- **Structure:** one Excel template (v2.0) with 20 sheets: Project Data, ESP Code, PDD (process cases, mechanical design data, loads), MD1/MD2 (casing, hopper, inlet/outlet, screens, insulators, profile standard, accessories), DT (dust transport), Support, Surface Treatment, Insulation, ED1–ED4 (electrical), MTS (component breakdown with sub-numbers 2001…2067), S&PD, Rev, ETS, and two hidden sheets with dropdown lists and the formulas that decode the ESP code. About 118 named ranges, so cells are stable per template version.
- **ESP code:** encodes the configuration in one string: chambers, ESP type, per field group the number of fields, field length (dm) and duct-spacing letter (H 300, M 400, S 500, X 600 mm), field widths (dm), field height (dm), hopper type (A1 trough, A2 pyramid, A3 chain scraper, A6 transversal trough, A7 transversal chain scraper), U-code (meaning unknown, ask), discharge-system code E<type><levels><drive> and collecting-system code C<drive><plate type><rapping position>.
- **What it gives the hopper:** hopper type, field sizes, plate thickness, profile standard, design pressure and temperature, dust density and collected dust, accessories (inspection door size, level indicators, heating), conveyor type, loads. **What it does not give:** hopper height, tiers, slot width, stiffening, valley angle: company design rules that the engineering owner must provide (E-02).
- **Weaknesses as machine input:** free text in numeric fields, decimal commas, mixed units, project-specific case names, a mix of design and procurement data.
- **Fabric filter:** out of scope (separate project).

### Next step when resuming: choose one

1. **TSD importer + ESP-code parser** (recommended first; deterministic, no AI): a module in the ESP domain package that reads a TSD of template v2.0 into a structured design basis with a cell reference as the source of every value, and checks the code against the expanded fields. Tests with a small synthetic TSD fixture only. Then a mapping table *TSD field → hopper input / rule / missing* to turn the E-02 questions into a concrete list for the engineering owner.
2. **ADR-0005 migration steps 1–3** (plan schema and generic executor, plan generator in `iaiep_esp.hopper.plan`, parity with the template), then step 6 accessories.

Both are independent. Later: retarget the F-3 test to *customer documents → TSD fields* (the requirement-analysis skill's target becomes the TSD), and after the hopper build an ESP envelope (GA) generator from the ESP code as the backbone for all sub-deliveries.

### Earlier hopper plan (still valid, after ADR-0005 migration)

(one commit per step, each checked against the reference delivery and the 12-variant sweep):

1. **Step 6 – accessories:** inspection door openings (bought-in standard door: place it and cut the opening), level indicator studs, protective covers, small corner plates. Reference part drawings in the hopper sub-delivery folder: protective covers, level stud, plates; the GA parts list gives quantities and masses. Read them first (render with pymupdf in `/tmp`, never commit).
2. **Conveyor:** a separate template (reference conveyor drawing in the same folder; wear plates are NM400/Hardox 400).
3. **Drawing set:** closer to the issued set (one drawing per welded panel plus the GA, sections, details, weld symbols) – the largest remaining piece, plan it as its own step.

**How to check a change** (all must pass before committing):

```bash
export UV_LINK_MODE=copy
uv sync --locked && uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
docker build --build-arg UID=$(id -u) -t iaiep-freecad-worker:dev workers/freecad   # after any worker change
uv run pytest -m integration
uv run iaiep-hopper domains/esp/examples/hopper_synthetic.toml --out out/hopper-synthetic
uv run iaiep-hopper data/reference/esp-project/hopper_case.toml \
    --reference data/reference/esp-project/hopper_reference.toml --out out/hopper-reference
```

Both runs currently give **77 checks, 0 failed**. The 12-variant flexibility sweep (shorter, longer, narrower, wider, taller, lower, pyramidal, 2 and 4 tiers, thicker plate, end wall bending inside a tier) was run with a temporary script; recreate it if needed (vary `parameters` of the synthetic case, resolve, calculate, run the worker, evaluate).

**Working rules carried over:**

- Confidential data (D-15): the real case files in `data/reference/` and drawings in `doc/drawings/` are git-ignored. Before every commit, scan the staged diff for customer names, drawing numbers, real dimensions and real profile designations; rule values derived from the delivery stay in the confidential case file.
- Engineering values are inputs with a source; derived rules are marked "not approved" until the engineering owner approves them (E-02).
- The platform calculates every part independently of the CAD worker and checks the model, BOM, DXF and PDF against it.
- FreeCAD quirks are in ADR-0001 (never pump `Gui.updateGui()`; notification area disabled). The dev container uses Docker outside of Docker: pipe files into containers, do not bind-mount.

**Open items waiting for people:**

- Product owner: open both TSDs in `doc/spec/` in Excel once to confirm they are intact after the cleanup, and ask the engineers what the ESP code's U-code means.
- Engineering owner: the questions in section 4 (joint allowances, height reference, profile standard, steel density, approval of the derived stiffener rules).
- Product owner: the reference input documents (customer specification, meeting notes) for the AI extraction test (F-3); then decide whether Ollama runs on the laptop GPU or a secured server (the current server is open on the LAN and holds an unsuitable model).
- **Decided 2026-11-23:** [ADR-0005](adr/0005-weldment-operations-and-editable-model.md) accepted. The hopper template becomes a plan generator in the ESP domain package, and a generic worker executes plans of general weldment operations (GE-04). The native FCStd file is a regenerated, inspectable output (spec §3.5/§12.1 updated). Step 6 waits for migration steps 1–3, so accessories are not written twice.

---

## 1. Key documents

| Document | Purpose |
|:---|:---|
| [IAIEP_Comprehensive_Specification_v3.0.md](IAIEP_Comprehensive_Specification_v3.0.md) | The specification. Single source of architectural intent (v3.0: governed AI skill layer, §6.8 and Appendix B). |
| Earlier specification versions | v1.2 is in git history (removed from `doc/` on 2026-11-23); v1.1 is in `archive/`. The history sections of this status file refer to v1.2. |
| [adr/0001-freecad-headless-execution.md](adr/0001-freecad-headless-execution.md) | FreeCAD spike results and decisions. |
| [adr/0002-llm-tool-calling.md](adr/0002-llm-tool-calling.md) | AI tool-calling spike results and decisions. |
| [adr/0003-repository-conventions.md](adr/0003-repository-conventions.md) | Layout, tooling, coding, testing and schema conventions. |
| [adr/0004-hopper-template-wall-panels.md](adr/0004-hopper-template-wall-panels.md) | Hopper template from wall panels; comparison with the reference delivery. |
| [adr/0005-weldment-operations-and-editable-model.md](adr/0005-weldment-operations-and-editable-model.md) | Accepted: template → plan of general weldment operations; regenerated native model. |
| [../workers/freecad/README.md](../workers/freecad/README.md) | FreeCAD worker: build, run, layout. |
| [../skills/](../skills/) | Draft platform skills: `engineering.requirement-analysis`, `esp.hopper-design` (spec §6.8). |
| [../.github/skills/freecad-worker/SKILL.md](../.github/skills/freecad-worker/SKILL.md) | Coding-assistant skill: FreeCAD worker rules and commands. |
| [../spikes/freecad-varset/README.md](../spikes/freecad-varset/README.md) | Editable-model spike (VarSet and expressions), evidence for ADR-0005. |
| [archive/IAIEP_Comprehensive_Specification_v1.1.md](archive/IAIEP_Comprehensive_Specification_v1.1.md) | Superseded version, kept for history only. |
| [../spikes/freecad-headless/README.md](../spikes/freecad-headless/README.md) | How to rerun the FreeCAD spike. |

## 2. What was done

### Session of 23 Nov 2026

Specification v3.0 reviewed and edited; skill catalogue and two draft skills; FreeCAD worker image rebuilt on this host; VarSet spike; ADR-0005 accepted; two external FreeCAD AI projects reviewed; coding-assistant skill; TSD analysed; confidential spreadsheets removed from unpushed history and sanitized TSDs cleaned. Details in "Where we left off".

### Sessions of 18–19 Nov 2026

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

### Phase 1: hopper pipeline and template — steps 1 to 5 done

- **FreeCAD worker** (`workers/freecad/`, ADR-0001 amended): two phases (headless build, then GUI offscreen PDF export). A deadlock of the FreeCAD GUI in offscreen mode was found and fixed (notification area; finding 9), verified with 60 of 60 export runs.
- **Template `esp.hopper` 0.6.0** (ADR-0004): trough or pyramidal hopper from flat wall panels in tiers, with panel and top gaps, tier beams and split top beams (channels), vertical stiffeners (angles), support column stubs (H sections) with column and base plates at the support grid, simplified support brackets and the internal bracing (tubes), from a profile catalogue and bracket plate lists in the input set. Outputs: native model, STEP AP242, drawing PDF (sheet and scale chosen automatically, title block, dimensions, parts list, notes, DRAFT marking), one DXF flat pattern per distinct panel, BOM.
- **Platform**: `iaiep.cad.worker` (runs a job in the worker container), `iaiep.checks`, and the ESP domain package `domains/esp` (`iaiep_esp.hopper`: input set with a source per value, independent calculation, checks, reference comparison, command `iaiep-hopper`).
- **Rules with overrides** (ADR-0004): stiffener spacing, support grid, beam extensions and top beam splits follow rules unless given explicitly; unapproved rules are reported as such.
- **Checks** (77 on the reference case, including that no part reaches inside the hopper): worker drawing checks; model against the independent calculation (panel sizes, slopes, valley angle, capacity, interferences, beams, stiffeners, column stubs and support plates); design criterion (reported as unapproved while it is a placeholder); BOM counts and masses of plates, profiles and support plates; each DXF read back; PDF text (status marking, main dimensions); native model opens with all parts visible.
- **Reference result**: generated panel plates match the issued part drawings within 0.3–2.5 mm and their masses within 0.2 %, except the middle-tier end panel (+21.8 mm, joint allowance to be explained by the engineering owner). Beam and stiffener counts match; lengths within 2 mm apart from the same plate differences; welded wall panel net masses within −0.9 % to +0.7 %. Top panels: plates within 2 mm; beams, stubs and support plates match; with the simplified brackets the welded top panels are −1.7 % (side) and −13.5 % (end; corner brackets simplified).

Run:

```bash
docker build --build-arg UID=$(id -u) -t iaiep-freecad-worker:dev workers/freecad
uv run iaiep-hopper domains/esp/examples/hopper_synthetic.toml --out out/hopper-synthetic
uv run iaiep-hopper data/reference/esp-project/hopper_case.toml \
    --reference data/reference/esp-project/hopper_reference.toml --out out/hopper-reference
```

## 3. Next steps

### Roadmap (agreed 2026-11-23, spec §25)

1. **Prove the engineering process with a real hopper** (Phase 1: F-1, F-2, F-5, F-6, GE-01 to GE-08). First migration steps 1–3 of ADR-0005, then only the hopper scope that F-1, F-2 and F-5 need.
2. **Prove the requirement-analysis skill** (Phase 1: F-3), in parallel with 1, as soon as the pre-design input documents arrive.
3. **Go/no-go decision** on F-1 to F-7, recorded in an ADR. Nothing below starts before it.
4. **Walking skeleton with the minimal skill registry and controlled execution** (Phase 2): tasks and executions in PostgreSQL, the hopper pipeline wrapped as tasks, the draft skill registered as the first skill.
5. **Engineering information model, CAD service, independent verification and a human gate** (Phases 4–6).
6. **Second equipment domain** (§24.4, Phase 8): a component that differs from a hopper (for example a tube sheet), chosen by the engineering owner.

### Phase 1 (developer / coding agent)

1. ADR-0005 migration steps 1–3 (plan schema and generic executor, plan generator in `iaiep_esp.hopper.plan`, parity with the template) before step 6.
2. **Step 6**, limited to what F-1, F-2 and F-5 need: inspection door openings, level studs, protective covers; then the conveyor template and a drawing set closer to the reference (sections, details).
3. Document extraction and AI extraction (Ollama) of the hopper input set, once the reference input documents are available (F-3). The draft skill package exists: `skills/engineering/requirement-analysis/` (spec §6.8.8, Appendix B); confidential evaluation cases go in the git-ignored `data/evaluation/`. The draft `skills/esp/hopper-design/` records the procedure of the `iaiep-hopper` pipeline; keep it in step with pipeline changes. All other skills are planned only (catalogue in spec §6.8.8); create a package when its work starts.
4. Store runs, inputs and check results in PostgreSQL with internal versions (spec §25 Phase 1).
5. GE-01 to GE-08, repeatability measurement (F-6) and the remaining F-criteria; then the go/no-go ADR.

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

- For the engineering owner: stiffener top extensions, bottom clearances and beam end extensions differ per tier in the reference (template inputs, ADR-0004 step 2). Is there a rule behind them? Also: which profile standard (thicknesses, kg/m table) applies, and the steel density (7850 assumed)? Is the hopper height measured to the underside of the top beams (assumed, with a 5 mm gap to the top plates)? Please review the stiffener spacing rules derived from the reference (max spacing per tier, heavy stiffeners on the column lines) for approval.
- Drawing: a long general-tolerance text overlaps the scale field in the title block (cosmetic, to fix).
- For the engineering owner: the reference shortens the middle-tier end panel by about 20 mm more than the template's joint rule, and the bottom-tier side panel by about 2.5 mm (ADR-0004). Which joint detail causes this?

- Taiga-S1 (Hugging Face CAD command model) was evaluated and **not adopted**: it drives the FreeCAD GUI step by step for simple PartDesign features and does not fit the template-first approach, drawings or document understanding.
- The laptop GPU (RTX 3500 Ada, 12 GB) was not used; the Ollama server on `ecsserver` is used instead.
- `ecsserver` holds an unsuitable model (`jimscard/adult-film-screenwriter-nsfw`); recommend `ollama rm` if the server is used for company work. The platform must only use explicitly approved models.
