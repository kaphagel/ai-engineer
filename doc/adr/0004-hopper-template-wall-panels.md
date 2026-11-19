# ADR-0004: ESP hopper template from flat wall panels, derived from a reference delivery

- **Status:** Accepted for Phase 1 (template status: draft, spec §12.4)
- **Date:** 2026-11-19
- **Related:** spec §1.2, §12.3, §12.4, §24.3, D-03, E-02, E-03, ADR-0001
- **Evidence:** `workers/freecad/iaiep_worker/hopper_geometry.py`, tests; reference comparison report (confidential, not committed)

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

Not yet modelled: stiffeners, tier beams, top panels and support interface, bracing, corner joint plates, welds, inspection door and level studs.

## Results on the reference case

Generated panel plates compared with the issued part drawings (sizes as on the drawings):

| Panel | Difference (width / height) | Mass difference |
|:---|:---|:---|
| Bottom tier, side | 0.0 / +2.5 mm | +1.0 kg (0.2 %) |
| Bottom tier, end | +1.1 / 0.0 mm | +0.1 kg |
| Middle tier, side | +0.3 / +0.1 mm | −0.3 kg |
| Middle tier, end | −0.9 / **+21.8 mm** | +1.5 kg |

The geometry, slopes and panel construction match. The open differences are joint allowances: the reference shortens the middle end panel by about another 20 mm and the bottom side panel by about 2.5 mm. These follow details not yet modelled (corner and tier joints) and need the engineering owner's explanation before the template rules are changed.

## Consequences

- Phase 1 F-1/F-2 comparisons use this reference case. The template grows step by step towards the issued construction: tier beams and stiffeners, then top panels and the support interface, then bracing and accessories.
- Template parameters for the reference case are read from the issued drawings; for new projects they come from the design basis and the AI extraction step (F-3).
