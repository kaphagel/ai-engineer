"""Validated input set for one hopper (spec §1.2 F-3, §10.5, §27.3).

Every value carries its source. Design criteria and design-basis items are engineering decisions
(spec §30.2, E-02/E-03): they are entered by a person, and a criterion that is not approved is
reported as such, never treated as approved.
"""

import tomllib
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

CASE_SCHEMA_VERSION = 1
DRAFT_STATUS = "DRAFT - NOT FOR FABRICATION"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Length(_Model):
    value: float = Field(gt=0)
    source: str = Field(min_length=1)


class OptionalLength(_Model):
    value: float = Field(ge=0)
    source: str = Field(min_length=1)


class Lengths(_Model):
    value: list[float] = Field(min_length=1)
    source: str = Field(min_length=1)


class Text(_Model):
    value: str = Field(min_length=1)
    source: str = Field(min_length=1)


class Texts(_Model):
    value: list[str]
    source: str = Field(min_length=1)


class Criterion(_Model):
    value: float
    source: str = Field(min_length=1)
    approved: bool


class HopperParameters(_Model):
    """Geometry parameters of template esp.hopper. Lengths in mm (spec §10.5)."""

    top_length_outside_mm: Length
    top_width_outside_mm: Length
    slot_length_inside_mm: Length
    slot_width_inside_mm: Length
    height_mm: Length
    end_wall_vertical_height_mm: OptionalLength
    tier_heights_mm: Lengths
    plate_thickness_mm: Length
    panel_gap_mm: OptionalLength

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        errors = []
        if abs(sum(self.tier_heights_mm.value) - self.height_mm.value) > 1e-6:
            errors.append(
                f"tier heights add up to {sum(self.tier_heights_mm.value):g}, not the height {self.height_mm.value:g}"
            )
        if any(t <= 0 for t in self.tier_heights_mm.value):
            errors.append("tier heights must be positive")
        if self.end_wall_vertical_height_mm.value >= self.height_mm.value:
            errors.append("the end wall vertical height must be less than the height")
        if self.slot_length_inside_mm.value >= self.top_length_outside_mm.value:
            errors.append("the slot length must be less than the top length")
        if self.slot_width_inside_mm.value >= self.top_width_outside_mm.value:
            errors.append("the slot width must be less than the top width")
        if errors:
            raise ValueError("; ".join(errors))
        return self

    def values(self) -> dict[str, float | list[float]]:
        return {name: getattr(self, name).value for name in type(self).model_fields}


class Material(_Model):
    designation: str = Field(min_length=1)
    standard: str = Field(min_length=1)
    density_kg_m3: Length


class DesignBasis(_Model):
    general_tolerances: Text
    standard_notes: Texts
    min_valley_angle_deg: Criterion


class DrawingInfo(_Model):
    title: str
    subtitle: str
    drawing_number: str = Field(pattern=r"^[A-Z0-9]+(-[A-Z0-9]+)+$")
    revision: str = Field(min_length=1, max_length=3)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    author: str
    department: str
    owner: str


class HopperCase(_Model):
    schema_version: int
    data_classification: str = Field(pattern="^(public|internal|confidential|restricted)$")
    parameters: HopperParameters
    material: Material
    design_basis: DesignBasis
    drawing: DrawingInfo

    @model_validator(mode="after")
    def _version(self) -> Self:
        if self.schema_version != CASE_SCHEMA_VERSION:
            raise ValueError(f"unsupported case schema_version {self.schema_version}")
        return self

    @classmethod
    def load(cls, path: Path) -> "HopperCase":
        with path.open("rb") as fh:
            return cls.model_validate(tomllib.load(fh))
