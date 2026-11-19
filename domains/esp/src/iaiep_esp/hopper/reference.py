"""Comparison of a generated hopper with an issued reference design (spec §1.2, F-1/F-2).

Informational: it lists differences for the engineering owner's review. It does not decide whether
a difference is acceptable. Reference data is confidential (D-15) and is never committed.
"""

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ReferencePlate(_Model):
    description: str
    drawing: str
    panel: str  # generated panel to compare with, for example "SideLeft-T2"
    size_mm: tuple[float, float]  # (width, height) as on the reference part drawing
    mass_kg: float | None = None


class ReferenceProfile(_Model):
    """Beams or stiffeners of one profile on one panel, as in the part drawing's parts list."""

    description: str
    drawing: str
    panel: str
    profile: str  # profile name in the case, for example "UPN200"
    quantity: int
    length_mm: float
    lengths_mm: list[float] | None = None  # when the pieces differ (split beams); length_mm is then the longest
    mass_kg: float  # total for the quantity


class ReferenceFitting(_Model):
    """Column or base plates on one panel, as in the part drawing's parts list."""

    description: str
    drawing: str
    panel: str
    kind: str  # "column plate" or "base plate"
    quantity: int
    size_mm: tuple[float, float, float]
    mass_kg: float  # total for the quantity


class ReferenceAssembly(_Model):
    """Welded panel (plate, tier beam on its top edge and its stiffeners): net mass from the drawing."""

    description: str
    drawing: str
    panel: str
    mass_kg: float


class ReferenceValue(_Model):
    description: str
    measurement: str  # key in the worker measurements, for example "valley_angle_deg"
    value: float


class Reference(_Model):
    name: str
    drawing: str
    data_classification: str = Field(pattern="^(internal|confidential|restricted)$")
    plates: list[ReferencePlate]
    profiles: list[ReferenceProfile] = []
    fittings: list[ReferenceFitting] = []
    assemblies: list[ReferenceAssembly] = []
    values: list[ReferenceValue] = []

    @classmethod
    def load(cls, path: Path) -> "Reference":
        with path.open("rb") as fh:
            return cls.model_validate(tomllib.load(fh))


class Difference(_Model):
    item: str
    reference: str
    generated: str
    difference: str
    largest_abs_mm: float | None = None


def compare(
    reference: Reference, result: dict[str, Any], density_kg_m3: float, thickness_mm: float
) -> list[Difference]:
    panels = result["measurements"]["panels"]
    rows = []
    for plate in reference.plates:
        measured = panels.get(plate.panel)
        if measured is None:
            rows.append(
                Difference(
                    item=plate.description, reference=_size(plate.size_mm), generated="not generated", difference="-"
                )
            )
            continue
        w, h = measured["flat_size_mm"]
        dw, dh = w - plate.size_mm[0], h - plate.size_mm[1]
        text = f"{dw:+.1f} / {dh:+.1f} mm"
        if plate.mass_kg is not None:
            mass = measured["flat_area_m2"] * thickness_mm / 1000 * density_kg_m3
            text += f"; mass {mass:.1f} kg vs {plate.mass_kg:g} kg ({mass - plate.mass_kg:+.1f})"
        rows.append(
            Difference(
                item=f"{plate.description} ({plate.drawing})",
                reference=_size(plate.size_mm),
                generated=f"{w:.1f} x {h:.1f} ({plate.panel})",
                difference=text,
                largest_abs_mm=max(abs(dw), abs(dh)),
            )
        )
    rows += _profiles(reference, result)
    rows += _fittings(reference, result)
    rows += _assemblies(reference, result, density_kg_m3, thickness_mm)
    for value in reference.values:
        generated = result["measurements"].get(value.measurement)
        if isinstance(generated, int | float):
            rows.append(
                Difference(
                    item=value.description,
                    reference=f"{value.value:g}",
                    generated=f"{generated:.2f}",
                    difference=f"{generated - value.value:+.2f}",
                )
            )
    return rows


def _part_masses(result: dict[str, Any]) -> dict[str, float]:
    return {part: item["unit_mass_kg"] for item in result["bom"] for part in item.get("parts", [])}


def _profiles(reference: Reference, result: dict[str, Any]) -> list[Difference]:
    measured = result["measurements"].get("profiles", {})
    masses = _part_masses(result)
    rows = []
    for ref in reference.profiles:
        found = [n for n, p in measured.items() if p["panel"] == ref.panel and p["profile"] == ref.profile]
        item = f"{ref.description} ({ref.drawing})"
        expected = f"{ref.quantity} x {ref.profile} L={ref.length_mm:g}, {ref.mass_kg:g} kg"
        if not found:
            rows.append(Difference(item=item, reference=expected, generated="not generated", difference="-"))
            continue
        lengths = sorted({round(measured[n]["length_mm"], 1) for n in found})
        mass = sum(masses.get(n, 0.0) for n in found)
        if ref.lengths_mm:
            pieces = sorted(measured[n]["length_mm"] for n in found)
            wanted = sorted(ref.lengths_mm)
            pairs = list(zip(pieces, wanted, strict=False))
            worst = max(pairs, key=lambda ab: abs(ab[0] - ab[1])) if pairs else (0.0, 0.0)
            furthest = ref.length_mm + worst[0] - worst[1]
            expected = (
                f"{ref.quantity} x {ref.profile} L={'/'.join(f'{x:g}' for x in ref.lengths_mm)}, {ref.mass_kg:g} kg"
            )
        else:
            furthest = max(lengths, key=lambda x: abs(x - ref.length_mm))
        rows.append(
            Difference(
                item=item,
                reference=expected,
                generated=f"{len(found)} x L={'/'.join(f'{x:g}' for x in lengths)}, {mass:.1f} kg ({ref.panel})",
                difference=f"qty {len(found) - ref.quantity:+d}; L {furthest - ref.length_mm:+.1f} mm; "
                f"mass {mass - ref.mass_kg:+.1f} kg",
                largest_abs_mm=abs(furthest - ref.length_mm),
            )
        )
    return rows


def _fittings(reference: Reference, result: dict[str, Any]) -> list[Difference]:
    measured = result["measurements"].get("fittings", {})
    masses = _part_masses(result)
    rows = []
    for ref in reference.fittings:
        found = [n for n, f in measured.items() if f["panel"] == ref.panel and f["kind"] == ref.kind]
        item = f"{ref.description} ({ref.drawing})"
        expected = f"{ref.quantity} x {'x'.join(f'{v:g}' for v in ref.size_mm)}, {ref.mass_kg:g} kg"
        if not found:
            rows.append(Difference(item=item, reference=expected, generated="not generated", difference="-"))
            continue
        sizes = sorted({tuple(round(v, 1) for v in measured[n]["size_mm"]) for n in found})
        mass = sum(masses.get(n, 0.0) for n in found)
        rows.append(
            Difference(
                item=item,
                reference=expected,
                generated=f"{len(found)} x {' / '.join('x'.join(f'{v:g}' for v in sz) for sz in sizes)}, {mass:.1f} kg",
                difference=f"qty {len(found) - ref.quantity:+d}; mass {mass - ref.mass_kg:+.1f} kg",
            )
        )
    return rows


def _assemblies(
    reference: Reference, result: dict[str, Any], density_kg_m3: float, thickness_mm: float
) -> list[Difference]:
    panels = result["measurements"]["panels"]
    profiles = result["measurements"].get("profiles", {})
    masses = _part_masses(result)
    rows = []
    for ref in reference.assemblies:
        item = f"{ref.description} ({ref.drawing})"
        if ref.panel not in panels:
            rows.append(
                Difference(item=item, reference=f"{ref.mass_kg:g} kg", generated="not generated", difference="-")
            )
            continue
        plate = panels[ref.panel]["flat_area_m2"] * thickness_mm / 1000 * density_kg_m3
        fittings = result["measurements"].get("fittings", {})
        attached = sum(masses.get(n, 0.0) for n, p in [*profiles.items(), *fittings.items()] if p["panel"] == ref.panel)
        mass = plate + attached
        rows.append(
            Difference(
                item=item,
                reference=f"{ref.mass_kg:g} kg",
                generated=f"{mass:.1f} kg (plate {plate:.1f} + attached {attached:.1f}, {ref.panel})",
                difference=f"{mass - ref.mass_kg:+.1f} kg ({(mass - ref.mass_kg) / ref.mass_kg:+.1%})",
            )
        )
    return rows


def _size(size: tuple[float, float]) -> str:
    return f"{size[0]:g} x {size[1]:g}"
