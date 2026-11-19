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


class ReferenceValue(_Model):
    description: str
    measurement: str  # key in the worker measurements, for example "valley_angle_deg"
    value: float


class Reference(_Model):
    name: str
    drawing: str
    data_classification: str = Field(pattern="^(internal|confidential|restricted)$")
    plates: list[ReferencePlate]
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


def _size(size: tuple[float, float]) -> str:
    return f"{size[0]:g} x {size[1]:g}"
