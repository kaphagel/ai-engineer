"""Checks on a CAD worker run: model against calculation, design criteria, BOM, DXF and PDF content.

An export that reports success is not proof of a correct output (ADR-0001), so the files themselves
are opened and checked here, independently of the worker's own checks.
"""

import re
import zipfile
from pathlib import Path
from typing import Any

from ezdxf.entities.polyline import Polyline
from ezdxf.filemanagement import readfile
from ezdxf.lldxf.const import DXFError
from pypdf import PdfReader

from iaiep.checks import CheckResult, CheckStatus
from iaiep_esp.hopper.calculation import HopperCalculation
from iaiep_esp.hopper.inputs import DRAFT_STATUS, HopperCase

LENGTH_TOL_MM = 0.5
ANGLE_TOL_DEG = 0.01
RELATIVE_TOL = 0.002


def evaluate(case: HopperCase, calc: HopperCalculation, result: dict[str, Any], out_dir: Path) -> list[CheckResult]:
    if not result.get("ok"):
        return [_fail("worker.ran", f"worker failed: {result.get('error')}", "worker")]
    checks = [_check("worker.ran", True, "worker completed", "worker")]
    checks += [
        CheckResult(id=f"worker.{c['id']}", status=CheckStatus(c["status"]), detail=c["detail"], source="worker")
        for c in result["drawing"]["checks"]
    ]
    checks += _model_against_calculation(calc, result["measurements"])
    checks.append(_valley_criterion(case, calc))
    checks += _bom(case, calc, result["bom"])
    checks += _flat_patterns(result["bom"], result["flat_patterns"], out_dir)
    checks += _pdf(calc, case, out_dir / result["files"]["drawing_pdf"])
    checks += _native_model(calc, out_dir / result["files"]["model"])
    return checks


def _model_against_calculation(calc: HopperCalculation, m: dict[str, Any]) -> list[CheckResult]:
    src = "model vs calculation"
    checks = [
        _check(
            "model.solids_valid",
            m["solids_valid"],
            "all plate solids valid" if m["solids_valid"] else "invalid solid",
            src,
        ),
        _check("model.no_interference", not m["interferences"], f"interferences: {m['interferences']}", src),
        _check(
            "model.panel_set",
            set(m["panels"]) == set(calc.panels),
            f"{len(m['panels'])} panels in the model, {len(calc.panels)} calculated",
            src,
        ),
    ]
    for name, expected in sorted(calc.panels.items()):
        measured = m["panels"].get(name)
        if measured is None:
            continue
        w, h = measured["flat_size_mm"]
        ok = abs(w - expected.width_mm) <= LENGTH_TOL_MM and abs(h - expected.height_mm) <= LENGTH_TOL_MM
        detail = f"model {w:.1f} x {h:.1f} mm, calculated {expected.width_mm:.1f} x {expected.height_mm:.1f} mm"
        checks.append(_check(f"model.panel_size.{name}", ok, detail, src))
    for key, angle in (
        ("side_wall_slope_deg", calc.side_wall_slope_deg),
        ("end_wall_slope_deg", calc.end_wall_slope_deg),
        ("valley_angle_deg", calc.valley_angle_deg),
    ):
        ok = abs(m[key] - angle) <= ANGLE_TOL_DEG
        checks.append(_check(f"model.{key}", ok, f"model {m[key]:.3f}°, calculated {angle:.3f}°", src))
    ok = abs(m["capacity_m3"] - calc.capacity_m3) <= RELATIVE_TOL * calc.capacity_m3
    checks.append(
        _check("model.capacity", ok, f"model {m['capacity_m3']:.2f} m³, calculated {calc.capacity_m3:.2f} m³", src)
    )
    return checks


def _valley_criterion(case: HopperCase, calc: HopperCalculation) -> CheckResult:
    criterion = case.design_basis.min_valley_angle_deg
    detail = f"valley angle {calc.valley_angle_deg:.1f}°, minimum {criterion.value:g}° (source: {criterion.source})"
    if calc.valley_angle_deg < criterion.value:
        return _fail("design.min_valley_angle", detail, "design criterion")
    status = CheckStatus.PASS if criterion.approved else CheckStatus.PASS_UNAPPROVED
    if not criterion.approved:
        detail += "; criterion NOT APPROVED"
    return CheckResult(id="design.min_valley_angle", status=status, detail=detail, source="design criterion")


def _bom(case: HopperCase, calc: HopperCalculation, bom: list[dict[str, Any]]) -> list[CheckResult]:
    src = "bom vs calculation"
    quantity = sum(item["quantity"] for item in bom)
    mass = sum(item["total_mass_kg"] for item in bom)
    expected = calc.plate_mass_kg(case.parameters.plate_thickness_mm.value, case.material.density_kg_m3.value)
    return [
        _check(
            "bom.plate_count",
            quantity == len(calc.panels),
            f"{quantity} plates in the BOM, {len(calc.panels)} calculated",
            src,
        ),
        _check(
            "bom.plate_mass",
            abs(mass - expected) <= RELATIVE_TOL * expected,
            f"BOM {mass:.1f} kg, calculated {expected:.1f} kg",
            src,
        ),
    ]


def _flat_patterns(bom: list[dict[str, Any]], patterns: list[dict[str, Any]], out_dir: Path) -> list[CheckResult]:
    """Each DXF must contain exactly one closed outline whose size matches the BOM."""
    checks = []
    sizes = {item["mark"]: item["flat_size_mm"] for item in bom}
    for pattern in patterns:
        check_id = f"dxf.{pattern['mark']}"
        try:
            doc = readfile(out_dir / pattern["file"])
        except (OSError, DXFError) as exc:
            checks.append(_fail(check_id, f"cannot read {pattern['file']}: {exc}", "dxf"))
            continue
        outlines = [e for e in doc.modelspace().query("POLYLINE") if isinstance(e, Polyline) and e.dxf.layer == "CUT"]
        if len(outlines) != 1 or not outlines[0].is_closed:
            checks.append(_fail(check_id, f"expected one closed CUT outline, found {len(outlines)}", "dxf"))
            continue
        xs = [v.dxf.location.x for v in outlines[0].vertices]
        ys = [v.dxf.location.y for v in outlines[0].vertices]
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        ew, eh = sizes[pattern["mark"]]
        ok = abs(w - ew) <= 0.1 and abs(h - eh) <= 0.1
        checks.append(_check(check_id, ok, f"{pattern['file']}: {w:.1f} x {h:.1f} mm (BOM {ew} x {eh})", "dxf"))
    return checks


def _pdf(calc: HopperCalculation, case: HopperCase, path: Path) -> list[CheckResult]:
    """The issued PDF must carry the status marking and the main dimensions as text."""
    try:
        text = " ".join(page.extract_text() or "" for page in PdfReader(path).pages)
    except (OSError, ValueError) as exc:
        return [_fail("pdf.readable", f"cannot read {path.name}: {exc}", "pdf")]
    words = set(text.split())
    p = case.parameters
    expected = {
        "top length (inside)": calc.inner_top_length_mm,
        "top width (inside)": calc.inner_top_width_mm,
        "slot length": p.slot_length_inside_mm.value,
        "slot width": p.slot_width_inside_mm.value,
        "height": p.height_mm.value,
    }
    missing = [f"{name} {value:.0f}" for name, value in expected.items() if f"{value:.0f}" not in words]
    return [
        _check("pdf.status_marking", DRAFT_STATUS in " ".join(text.split()), f"'{DRAFT_STATUS}' on the drawing", "pdf"),
        _check(
            "pdf.main_dimensions",
            not missing,
            f"missing: {missing}" if missing else "all main dimensions present",
            "pdf",
        ),
    ]


def _native_model(calc: HopperCalculation, path: Path) -> list[CheckResult]:
    """The native model must open in FreeCAD showing the 3D plates (not hidden, camera fitted)."""
    src = "native model"
    try:
        with zipfile.ZipFile(path) as fcstd:
            gui = fcstd.read("GuiDocument.xml").decode("utf-8")
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        return [_fail("native.gui_document", f"{path.name} has no readable GUI document: {exc}", src)]
    hidden = []
    for name in calc.panels:
        object_name = name.replace("-", "_")
        start = gui.find(f'<ViewProvider name="{object_name}"')
        block = gui[start : gui.find("</ViewProvider>", start)] if start >= 0 else ""
        visible = re.search(r'name="Visibility"[^>]*>\s*<Bool value="true"', block)
        if not visible:
            hidden.append(name)
    camera = re.search(r"height ([0-9.]+)", gui)
    fitted = camera is not None and float(camera.group(1)) > 100.0
    return [
        _check("native.plates_visible", not hidden, f"hidden: {hidden}" if hidden else "all plates visible", src),
        _check("native.camera_fitted", fitted, f"camera height {camera.group(1) if camera else '?'} mm", src),
    ]


def _check(check_id: str, ok: bool, detail: str, source: str) -> CheckResult:
    return CheckResult(id=check_id, status=CheckStatus.PASS if ok else CheckStatus.FAIL, detail=detail, source=source)


def _fail(check_id: str, detail: str, source: str) -> CheckResult:
    return _check(check_id, False, detail, source)
