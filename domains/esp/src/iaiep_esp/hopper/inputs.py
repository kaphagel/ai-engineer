"""Validated input set for one hopper (spec §1.2 F-3, §10.5, §27.3).

Every value carries its source. Design criteria and design-basis items are engineering decisions
(spec §30.2, E-02/E-03): they are entered by a person, and a criterion that is not approved is
reported as such, never treated as approved.
"""

import tomllib
from pathlib import Path
from typing import Literal, Self

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


class Profile(_Model):
    """Rolled section from a catalogue. The mass per metre is used for the BOM; the dimensions only
    shape the 3D model (nominal, no root radii)."""

    kind: Literal["channel", "angle"]
    designation: str = Field(min_length=1)
    standard: str = Field(min_length=1)
    material: str = Field(min_length=1)
    depth_mm: float = Field(gt=0)  # channel: web depth; angle: outstanding leg
    width_mm: float = Field(gt=0)  # channel: flange width; angle: leg on the plate
    web_thickness_mm: float = Field(gt=0)
    flange_thickness_mm: float = Field(gt=0)
    mass_per_m_kg: float = Field(gt=0)
    source: str = Field(min_length=1)


class TierBeams(_Model):
    """Channels along the top edge of every tier except the topmost."""

    side_profile: str
    end_profile: str
    # Beam length = panel top edge + 2 x extension; one value per tier joint, bottom joint first.
    side_end_extensions_mm: list[float]
    end_end_extensions_mm: list[float]
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _not_negative(self) -> Self:
        if any(x < 0 for x in [*self.side_end_extensions_mm, *self.end_end_extensions_mm]):
            raise ValueError("beam end extensions must not be negative")
        return self


class StiffenerLayout(_Model):
    """Vertical stiffeners on one wall type in one tier, dimensioned like the part drawings: bays
    (centre distances) symmetric about the panel centreline, profiles listed left to right as seen
    from outside the hopper."""

    wall: Literal["side", "end"]
    tier: int = Field(ge=1)
    bays_mm: list[float]
    profiles: list[str] = Field(min_length=1)
    bottom_clearance_mm: float = Field(ge=0)  # above the tier bottom
    top_extension_mm: float = Field(ge=0)  # beyond the panel top edge, where a tier beam is above
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _counts(self) -> Self:
        if any(b <= 0 for b in self.bays_mm):
            raise ValueError("bays must be positive")
        if len(self.profiles) != len(self.bays_mm) + 1:
            raise ValueError(f"{len(self.bays_mm)} bays need {len(self.bays_mm) + 1} profiles")
        return self


class Stiffening(_Model):
    tier_beams: TierBeams | None = None
    stiffeners: list[StiffenerLayout] = []


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
    profiles: dict[str, Profile] = {}
    stiffening: Stiffening | None = None
    design_basis: DesignBasis
    drawing: DrawingInfo

    @model_validator(mode="after")
    def _version(self) -> Self:
        if self.schema_version != CASE_SCHEMA_VERSION:
            raise ValueError(f"unsupported case schema_version {self.schema_version}")
        return self

    @model_validator(mode="after")
    def _profiles_exist(self) -> Self:
        st = self.stiffening
        if st is None:
            return self
        errors = []
        wanted = [
            (p, "channel") for p in ((st.tier_beams.side_profile, st.tier_beams.end_profile) if st.tier_beams else ())
        ]
        wanted += [(p, "angle") for layout in st.stiffeners for p in layout.profiles]
        for name, kind in wanted:
            if name not in self.profiles or self.profiles[name].kind != kind:
                errors.append(f"profile {name!r} must be a {kind} in [profiles]")
        tiers = len(self.parameters.tier_heights_mm.value)
        if st.tier_beams is not None:
            beams = st.tier_beams
            for wall, values in (("side", beams.side_end_extensions_mm), ("end", beams.end_end_extensions_mm)):
                if len(values) != tiers - 1:
                    errors.append(f"{wall} beam end extensions: {len(values)} given, {tiers - 1} tier joints")
        seen = set()
        for layout in st.stiffeners:
            if layout.tier > tiers:
                errors.append(f"stiffeners on tier {layout.tier}, but there are {tiers} tiers")
            if (layout.wall, layout.tier) in seen:
                errors.append(f"two stiffener layouts for the {layout.wall} wall, tier {layout.tier}")
            seen.add((layout.wall, layout.tier))
        if errors:
            raise ValueError("; ".join(sorted(set(errors))))
        return self

    @classmethod
    def load(cls, path: Path) -> "HopperCase":
        with path.open("rb") as fh:
            return cls.model_validate(tomllib.load(fh))
