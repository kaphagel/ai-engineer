# ADR-0004: ESP hopper template from flat wall panels, derived from a reference delivery

- **Status:** Accepted for Phase 1 (template status: draft, spec §12.4)
- **Date:** 2026-11-19
- **Related:** spec §1.2, §12.3, §12.4, §24.3, D-03, E-02, E-03, ADR-0001
- **Evidence:** `workers/freecad/iaiep_worker/hopper_geometry.py`, `hopper_profiles.py`, tests; reference comparison report (confidential, not committed)

## Context

The first template (v0.1.0) modelled the simple pyramidal hopper described in spec §24.3 with synthetic values. The product owner then provided a complete issued ESP delivery (2025, released drawings, delivery lists, part drawings). Its bottom hopper is a **trough hopper**: a long rectangular top opening narrowing to a narrow slot above a drag-chain conveyor, with end walls that are vertical in the lowest tier. It is built from thin wall panels in horizontal tiers, with stiffeners, tier beams, top panels with support beams, and bracing. Its dimensions are recorded only in the confidential reference files.

The reference data is confidential (D-15): it is stored in git-ignored folders (`doc/drawings/`, `data/reference/`) and used only with local tools and models.

## Decision

Template `esp.hopper` 0.2.0 replaces 0.1.0 and generalizes it:

- Side walls slope from the slot width to the top width over the full height. End walls are vertical up to a given height, then slope to the top length. A vertical height of zero and a square slot give the pyramidal hopper.
- The walls are divided into tiers; each tier of each wall is one flat panel (split where an end wall changes slope inside a tier). At each tier joint the upper panel starts a given gap above the joint, measured along the wall.
- The top opening is given on the outside of the plates and the slot on the inside, as on the reference drawing; the inside top dimensions are derived.
- Panel edges are square to the plate; adjacent walls meet at the inner corner line.
- Every input value carries its source. Tolerances, standard notes (weld quality, execution class) and design criteria come from the design basis; the minimum valley angle stays a labelled, unapproved placeholder until the engineering owner sets it (E-02).
- The geometry rules are pure Python (unit-tested). The platform calculates the same quantities with a separate implementation and checks the model against it.

Not yet modelled: bracing, corner joint plates, welds, inspection door and level studs.

### Step 2 (template 0.3.0): tier beams and stiffeners

- **Tier beams:** a channel on the top edge of every tier except the topmost, one per wall and joint, web horizontal under the upper panel, flanges hanging down outside the lower panel (as in the reference part drawings). Its length is the top edge of the lower panel plus an end extension at each end.
- **Stiffeners:** angles on the outer face of a panel, square to its top edge, one leg on the plate. Positions are given as bays (centre distances) symmetric about the panel centreline, with a profile per position, because the part drawings dimension them that way. A stiffener runs from the panel's bottom edge (at least a clearance above the plate bottom) to the top edge, plus an extension where a tier beam is above.
- **Inputs, not rules:** beam end extensions (per joint and wall type), stiffener top extensions and bottom clearances (per layout) differ between tiers in the reference without a rule we could derive. They are input values with sources from the part drawings, flagged for the engineering owner, rather than invented formulas.
- **Profiles:** a catalogue in the input set (kind, nominal dimensions, mass per metre, material, source). The BOM uses the mass per metre; the dimensions only shape the 3D model (no root radii).
- **Simplified connections:** copes, cut-outs and corner connections are not modelled. Overlaps of parts at connections are listed in the report, not counted as errors; plates overlapping each other, or a profile cutting into the plate it stands on, still fail.
- The platform calculates every beam and stiffener (set, profile, length, mass) independently and checks the model and the BOM against it.
- Drawing dimensions whose points are hidden behind profiles are attached to cosmetic vertices at the exact model points.

### Step 3 (template 0.4.0): top beams and support interface

- **Top gap:** the top panels end a given distance below the top (z = height, taken as the underside of the top beams), measured along the wall, as the reference sections show.
- **Top beams:** channels resting on the top edge of the topmost tier, placed like the tier beams, split into segments at given positions along the beam (the reference splits the side beams at the support columns). End extensions may be negative.
- **Supports:** an H-section column stub at every support grid point on the hopper perimeter, with a column plate on top (top level an input; the reference has it flush with the top beams) and a base plate below. Corner points belong to the end walls, the others to the side walls. The side column plate may be offset away from the hopper axis.
- **Top-tier stiffeners:** single stiffeners can stop a given distance below the top (they end under the support brackets in the reference).
- **Checks:** model against the calculation for top beams, stub positions and levels, and every column and base plate (size, position, height); BOM counts and masses; the support grid dimensions on the drawing and in the PDF text. Column and base plates do not stand on a panel plate, so their overlaps with plate edges (local cut-outs in reality) are reported as connection overlaps.
- **Not modelled:** the bracket plates and flat bars between the stubs and the top panels, the pins on the column plates, the horizontal flat bars on the top panels.

### Step 4 (template 0.5.0): support brackets

The issued brackets consist of about ten shaped plates each. They are modelled in a simplified, checkable arrangement:

- **Plates from the input:** the bracket plates of the issued parts list (thickness, size, quantity per support), each with a role: *gusset* (on the column line between stub and wall; shape from the geometry), *back* (against the stub, in a row along the wall), *side* (at the ends of the back row), *bottom* (horizontal under the bracket), *bar* (flat bars on the outer wall face beside the bracket). Side brackets and corner brackets have separate lists; corner brackets are moved along the end wall so they stay on the plate.
- **Cut to the wall:** every bracket plate is trimmed by the outer wall face, as the real plates are.
- **Stiffeners under brackets:** a spacing rule can stop the side-wall stiffeners of the top tier that lie under a bracket a given distance below its bottom.
- **New check `model.outside_hopper`:** no part may reach more than 5 mm inside the inner plate surfaces (the space for the bulk material). It found the untrimmed bracket plates and a column plate assumption. The 5 mm tolerance allows the tier beams, which are exposed to the bulk material through the panel gaps.
- The platform calculates every bracket plate (bounding box and volume) independently; the model and BOM are checked against it.
- The reference column plates sit on top of the top beams (the 800 mm column dimension and section H-H of the side top panel).

Result on the reference case: welded top side panel −1.7 %, welded top end panel −13.5 %. The corner brackets of the delivery are arranged diagonally between the corner column and both walls; the simplified arrangement trims them too much (open item, together with the corner joint details).

### Flexibility: rules with explicit overrides

A parameter sweep (shorter, longer, narrower, wider, taller, lower, pyramidal, two and four tiers, thicker plate, end wall bending inside a tier) showed that the panel geometry adapts, but the stiffening did not: stiffener bays, the support grid and per-joint beam extensions were fixed numbers read from drawings. The sweep also found overlapping plates where an end wall bends inside a tier; they are now mitred on the bisector plane.

Decision: the stiffening is defined by **engineering rules, with explicit values as overrides** (`iaiep_esp.hopper.rules`). The platform resolves the rules into explicit values before the calculation and the CAD job, so the worker and the independent calculation are unchanged and the report shows which values came from a rule.

- **Stiffeners:** per wall type and tier position (bottom, middle, top) a maximum spacing, bottom clearance and top extension. On the side walls a heavier profile stands on every inner support column line; each stretch between the panel ends and the column lines is divided into the fewest equal bays not longer than the maximum spacing. Rules need a support grid symmetric about the centre.
- **Tier beams:** one end extension for every joint, or one per joint. **Top beams:** split at the inner column lines, or at given positions.
- **Supports:** corner columns at given offsets outside the outer plate faces, equal bays between them; or explicit grid lines.
- An explicit stiffener layout for a wall type and tier always wins over the rule.
- Rules are design decisions (E-02): a check reports layouts made by unapproved rules as `pass_unapproved_criterion`.
- Rule values derived from the reference delivery are company know-how and stay in the confidential case file; the committed synthetic example uses invented values.

On the reference case, the derived rules alone (no explicit layouts, rule-based grid) reproduce the issued support grid exactly and every stiffener count except one extra on the bottom side panels; welded wall panel masses stay within 0.0–0.7 %. They do not shorten stiffeners under the support brackets (step 4).

## Results on the reference case

Generated panel plates compared with the issued part drawings (sizes as on the drawings):

| Panel | Difference (width / height) | Mass difference |
|:---|:---|:---|
| Bottom tier, side | 0.0 / +2.5 mm | +1.0 kg (0.2 %) |
| Bottom tier, end | +1.1 / 0.0 mm | +0.1 kg |
| Middle tier, side | +0.3 / +0.1 mm | −0.3 kg |
| Middle tier, end | −0.9 / **+21.8 mm** | +1.5 kg |

Step 2, on the same case: profile counts match the part drawings on all four reference panels; profile lengths match within 1 mm except where they follow the plate differences above (+2.5 mm bottom side, +21.8 mm middle end). Net masses of the welded panels: −0.9 % (bottom side, which also has small flat bars not modelled), +0.1 %, +0.0 % and +0.7 %.

Step 3, on the same case: top panel plates match within 2 mm and 0.1 %; top beams, column stubs, column and base plates and top-tier stiffeners match in number, and in length within 2 mm. The welded top panels are 24–36 % lighter than the drawings because the support brackets are not modelled yet.

The geometry, slopes and panel construction match. The open differences are joint allowances: the reference shortens the middle end panel by about another 20 mm and the bottom side panel by about 2.5 mm. These follow details not yet modelled (corner and tier joints) and need the engineering owner's explanation before the template rules are changed.

## Consequences

- Phase 1 F-1/F-2 comparisons use this reference case. The template grows step by step towards the issued construction: tier beams and stiffeners (done, 0.3.0), top beams and support interface (done, 0.4.0), then support brackets, bracing and accessories.
- Template parameters for the reference case are read from the issued drawings; for new projects they come from the design basis and the AI extraction step (F-3).
