"""Phase 1 command-line pipeline for one hopper (spec §25 Phase 1: simple orchestration).

    iaiep-hopper CASE.toml --out DIR [--reference REFERENCE.toml]

Validates the input set, calculates the geometry, runs the FreeCAD worker, checks every output and
writes report.json and report.md next to the outputs. Exit code: 0 all checks passed, 1 a check
failed, 2 the run could not be completed.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from iaiep.cad.worker import WorkerError, WorkerSettings, run_job
from iaiep.checks import CheckResult, CheckStatus
from iaiep_esp.hopper import TEMPLATE_ID, TEMPLATE_VERSION
from iaiep_esp.hopper.calculation import HopperCalculation, calculate
from iaiep_esp.hopper.checks import evaluate
from iaiep_esp.hopper.inputs import DRAFT_STATUS, HopperCase
from iaiep_esp.hopper.reference import Difference, Reference, compare

JOB_SCHEMA_VERSION = 1


def build_job(case: HopperCase) -> dict[str, Any]:
    """CAD job for the worker. The status is always DRAFT: the release gate is disabled (spec §30.2)."""
    d = case.drawing
    return {
        "schema_version": JOB_SCHEMA_VERSION,
        "template": {"id": TEMPLATE_ID, "version": TEMPLATE_VERSION},
        "parameters": case.parameters.values(),
        "material": {
            "designation": case.material.designation,
            "standard": case.material.standard,
            "density_kg_m3": case.material.density_kg_m3.value,
        },
        "drawing": {
            "title": d.title,
            "subtitle": d.subtitle,
            "drawing_number": d.drawing_number,
            "revision": d.revision,
            "date": d.date,
            "author": d.author,
            "department": d.department,
            "owner": d.owner,
            "status": DRAFT_STATUS,
            "general_tolerances": case.design_basis.general_tolerances.value,
            "standard_notes": case.design_basis.standard_notes.value,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="iaiep-hopper", description="Generate and check an ESP hopper.")
    parser.add_argument("case", type=Path, help="hopper input set (TOML)")
    parser.add_argument("--out", type=Path, required=True, help="output directory (replaced)")
    parser.add_argument("--reference", type=Path, help="issued reference design to compare with (TOML)")
    args = parser.parse_args(argv)

    try:
        case = HopperCase.load(args.case)
        reference = Reference.load(args.reference) if args.reference else None
    except (OSError, ValueError, ValidationError) as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 2
    calc = calculate(case.parameters)
    started = datetime.now(UTC)
    try:
        run = run_job(build_job(case), args.out, WorkerSettings.from_env())
    except WorkerError as exc:
        print(f"CAD worker error: {exc}", file=sys.stderr)
        return 2

    checks = evaluate(case, calc, run.result, args.out)
    differences = (
        compare(reference, run.result, case.material.density_kg_m3.value, case.parameters.plate_thickness_mm.value)
        if reference and run.result.get("ok")
        else []
    )
    report = {
        "generated_at": started.isoformat(timespec="seconds"),
        "case_file": str(args.case),
        "data_classification": case.data_classification,
        "template": {"id": TEMPLATE_ID, "version": TEMPLATE_VERSION},
        "freecad_version": run.result.get("freecad_version"),
        "worker_image": run.image_id,
        "files_sha256": run.files_sha256,
        "inputs": case.model_dump(),
        "calculation": _calculation_dict(calc),
        "checks": [c.model_dump(mode="json") for c in checks],
        "reference": reference.name if reference else None,
        "differences": [d.model_dump() for d in differences],
        "geometry_signature": run.result.get("geometry_signature", {}).get("sha256"),
    }
    (args.out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (args.out / "report.md").write_text(_markdown(case, calc, checks, reference, differences, report), encoding="utf-8")

    failed = [c for c in checks if c.failed]
    unapproved = [c for c in checks if c.status is CheckStatus.PASS_UNAPPROVED]
    print(
        f"{len(checks)} checks: {len(failed)} failed, {len(unapproved)} against unapproved criteria. "
        f"Report: {args.out / 'report.md'}"
    )
    for c in failed:
        print(f"  FAIL {c.id}: {c.detail}")
    return 1 if failed else 0


def _calculation_dict(calc: HopperCalculation) -> dict[str, Any]:
    return {
        "inner_top_length_mm": round(calc.inner_top_length_mm, 3),
        "inner_top_width_mm": round(calc.inner_top_width_mm, 3),
        "side_wall_slope_deg": round(calc.side_wall_slope_deg, 4),
        "end_wall_slope_deg": round(calc.end_wall_slope_deg, 4),
        "valley_angle_deg": round(calc.valley_angle_deg, 4),
        "capacity_m3": round(calc.capacity_m3, 4),
        "panels": {k: [round(v.width_mm, 2), round(v.height_mm, 2)] for k, v in calc.panels.items()},
    }


def _markdown(
    case: HopperCase,
    calc: HopperCalculation,
    checks: list[CheckResult],
    reference: Reference | None,
    differences: list[Difference],
    report: dict[str, Any],
) -> str:
    failed = sum(c.failed for c in checks)
    lines = [
        f"# Hopper report: {case.drawing.title} ({case.drawing.drawing_number} rev {case.drawing.revision})",
        "",
        f"- Status: **{DRAFT_STATUS}**",
        f"- Data classification: {case.data_classification}",
        f"- Template: {TEMPLATE_ID} {TEMPLATE_VERSION}; FreeCAD {report['freecad_version']}",
        f"- Generated: {report['generated_at']}",
        f"- Checks: {len(checks)}, failed: {failed}",
        "",
        "## Calculated geometry",
        "",
        f"- Inside top opening: {calc.inner_top_length_mm:.1f} x {calc.inner_top_width_mm:.1f} mm",
        f"- Wall slopes: side {calc.side_wall_slope_deg:.2f}°, end {calc.end_wall_slope_deg:.2f}°; "
        f"valley angle {calc.valley_angle_deg:.2f}°",
        f"- Capacity: {calc.capacity_m3:.2f} m³",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "|:---|:---|:---|",
        *[f"| {c.id} | {c.status.value} | {c.detail} |" for c in checks],
    ]
    if reference:
        lines += [
            "",
            f"## Comparison with reference: {reference.name} ({reference.drawing})",
            "",
            "Informational; the engineering owner decides whether differences matter.",
            "",
            "| Item | Reference | Generated | Difference |",
            "|:---|:---|:---|:---|",
            *[f"| {d.item} | {d.reference} | {d.generated} | {d.difference} |" for d in differences],
        ]
    lines += [
        "",
        "## Output files (SHA-256)",
        "",
        *[f"- `{n}` {h[:16]}" for n, h in report["files_sha256"].items()],
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
