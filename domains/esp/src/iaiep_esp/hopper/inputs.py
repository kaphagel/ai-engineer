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
    top_gap_mm: OptionalLength | None = None  # top panels end this far below the top, along the wall

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
        return {name: field.value for name in type(self).model_fields if (field := getattr(self, name)) is not None}


class Material(_Model):
    designation: str = Field(min_length=1)
    standard: str = Field(min_length=1)
    density_kg_m3: Length


class Profile(_Model):
    """Rolled section from a catalogue. The mass per metre is used for the BOM; the dimensions only
    shape the 3D model (nominal, no root radii)."""

    kind: Literal["channel", "angle", "h_section", "tube"]
    designation: str = Field(min_length=1)
    standard: str = Field(min_length=1)
    material: str = Field(min_length=1)
    depth_mm: float = Field(gt=0)  # channel, H: web depth; angle: outstanding leg; tube: outside diameter
    width_mm: float = Field(gt=0)  # channel, H: flange width; angle: leg on the plate; tube: outside diameter
    web_thickness_mm: float = Field(gt=0)
    flange_thickness_mm: float = Field(gt=0)
    mass_per_m_kg: float = Field(gt=0)
    source: str = Field(min_length=1)


class TierBeams(_Model):
    """Channels along the top edge of every tier except the topmost."""

    side_profile: str
    end_profile: str
    # Beam length = panel top edge + 2 x extension. Either one value for every joint, or one value per
    # tier joint (bottom joint first), for example as read from issued part drawings.
    side_end_extension_mm: float | None = None
    end_end_extension_mm: float | None = None
    side_end_extensions_mm: list[float] | None = None
    end_end_extensions_mm: list[float] | None = None
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _one_way(self) -> Self:
        for wall, single, per_joint in (
            ("side", self.side_end_extension_mm, self.side_end_extensions_mm),
            ("end", self.end_end_extension_mm, self.end_end_extensions_mm),
        ):
            if (single is None) == (per_joint is None):
                raise ValueError(f"give either {wall}_end_extension_mm or {wall}_end_extensions_mm")
            if any(x < 0 for x in [single or 0.0, *(per_joint or [])]):
                raise ValueError("beam end extensions must not be negative")
        return self

    def extensions(self, wall: str, joints: int) -> list[float]:
        single, per_joint = (
            (self.side_end_extension_mm, self.side_end_extensions_mm)
            if wall == "side"
            else (self.end_end_extension_mm, self.end_end_extensions_mm)
        )
        return list(per_joint) if per_joint is not None else [single or 0.0] * joints


class StiffenerLayout(_Model):
    """Vertical stiffeners on one wall type in one tier, dimensioned like the part drawings: bays
    (centre distances) symmetric about the panel centreline, profiles listed left to right as seen
    from outside the hopper."""

    wall: Literal["side", "end"]
    tier: int = Field(ge=1)
    bays_mm: list[float]
    profiles: list[str] = Field(min_length=1)
    bottom_clearance_mm: float = Field(ge=0)  # above the tier bottom
    # Beyond the panel top edge where a tier or top beam is above; negative: stops below the edge.
    top_extension_mm: float
    # Per stiffener: further shortening at the top (stiffeners stopping below brackets); default none.
    stops_below_top_mm: list[float] | None = None
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _counts(self) -> Self:
        if any(b <= 0 for b in self.bays_mm):
            raise ValueError("bays must be positive")
        if len(self.profiles) != len(self.bays_mm) + 1:
            raise ValueError(f"{len(self.bays_mm)} bays need {len(self.bays_mm) + 1} profiles")
        stops = self.stops_below_top_mm
        if stops is not None and (len(stops) != len(self.profiles) or any(x < 0 for x in stops)):
            raise ValueError("stops_below_top_mm needs one value of at least 0 per stiffener")
        return self


class TopBeams(_Model):
    """Channels on the top edge of the topmost tier, split into segments (for example at the columns)."""

    side_profile: str
    end_profile: str
    side_end_extension_mm: float  # beam length = plate top edge + 2 x extension; may be negative
    end_end_extension_mm: float
    side_splits_mm: list[float] = []  # joint positions along the beam, from the centreline
    end_splits_mm: list[float] = []
    split_at_columns: bool = False  # side beams split at the inner support column lines instead
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _one_way(self) -> Self:
        if self.split_at_columns and self.side_splits_mm:
            raise ValueError("give either side_splits_mm or split_at_columns")
        return self


class Supports(_Model):
    """Support column stubs at the support grid points on the hopper perimeter (corners on the end walls)."""

    # Either the column lines (grid_x_mm along the hopper, grid_y_mm the two lines across), or a rule:
    # equal bays between corner columns placed at the given offsets outside the outer plate faces.
    grid_x_mm: list[float] | None = Field(default=None, min_length=2)
    grid_y_mm: list[float] | None = Field(default=None, min_length=2, max_length=2)
    column_bays: int | None = Field(default=None, ge=1)
    corner_offset_x_mm: float | None = None
    side_offset_y_mm: float | None = None
    stub_profile: str
    stub_length_mm: float = Field(gt=0)
    column_plate_top_above_top_mm: float  # top of the column plate above the hopper top
    corner_column_plate_mm: list[float] = Field(min_length=3, max_length=3)  # along x, along y, thickness
    side_column_plate_mm: list[float] = Field(min_length=3, max_length=3)
    side_column_plate_outward_offset_mm: float = 0  # centre moved away from the hopper axis
    base_plate_mm: list[float] = Field(min_length=3, max_length=3)
    plate_material: str = Field(min_length=1)
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _grid(self) -> Self:
        explicit = self.grid_x_mm is not None and self.grid_y_mm is not None
        rule = None not in (self.column_bays, self.corner_offset_x_mm, self.side_offset_y_mm)
        if explicit == rule:
            raise ValueError(
                "give either grid_x_mm and grid_y_mm, or column_bays, corner_offset_x_mm, side_offset_y_mm"
            )
        if self.grid_x_mm is not None and (
            self.grid_x_mm != sorted(self.grid_x_mm) or len(set(self.grid_x_mm)) != len(self.grid_x_mm)
        ):
            raise ValueError("grid_x_mm must be increasing")
        if self.grid_y_mm is not None and (self.grid_y_mm[0] >= 0 or self.grid_y_mm[1] <= 0):
            raise ValueError("grid_y_mm needs one line on each side of the hopper axis")
        if any(v <= 0 for v in [*self.corner_column_plate_mm, *self.side_column_plate_mm, *self.base_plate_mm]):
            raise ValueError("plate sizes must be positive")
        return self


class BracketPlate(_Model):
    """One plate of a support bracket (simplified arrangement, see ADR-0004).

    gusset: between the stub and the sloped wall, on the column line; its shape follows the geometry
        (only the thickness is given).
    back: vertical, against the inner face of the stub, in a row along the wall centred on the bracket;
        size = (along the wall, height).
    side: vertical, square to the wall at the ends of the back row; size = (towards the hopper, height).
    bottom: horizontal under the bracket, in a row along the wall; size = (along the wall, towards the
        hopper from the stub face).
    bar: horizontal flat bar on the outer wall face, `level_mm` above the bracket bottom, placed beside
        the bracket alternately left and right; size = (along the wall, outward from the wall).
    """

    role: Literal["gusset", "back", "side", "bottom", "bar"]
    thickness_mm: float = Field(gt=0)
    size_mm: list[float] | None = Field(default=None, min_length=2, max_length=2)
    quantity: int = Field(default=1, ge=1)
    level_mm: float = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _size(self) -> Self:
        if (self.role == "gusset") != (self.size_mm is None):
            raise ValueError("give size_mm for every bracket plate except the gusset")
        if self.size_mm is not None and min(self.size_mm) <= 0:
            raise ValueError("bracket plate sizes must be positive")
        return self


class Brackets(_Model):
    """Brackets connecting each support stub to the top panel it belongs to."""

    depth_mm: float = Field(gt=0)  # from the top (z = height) down to the bracket bottom
    side: list[BracketPlate] = Field(min_length=1)  # brackets at the side column lines
    corner: list[BracketPlate] = Field(min_length=1)  # brackets at the corner columns (on the end walls)
    material: str = Field(min_length=1)
    source: str = Field(min_length=1)


class Strut(_Model):
    """Horizontal tube across the hopper (between the side walls) at a tier joint, with an end plate at
    each end passing through the panel gap."""

    joint: int | None = Field(default=None, ge=1)  # 1 = between tiers 1 and 2; none: every tier joint
    tube_profile: str
    end_plate_mm: list[float] = Field(min_length=3, max_length=3)  # along the strut, height, thickness
    overhang_mm: float  # end plate beyond the inner wall face, each end
    plate_projection_mm: float = Field(gt=0)  # end plate beyond the tube end
    level_offset_mm: float = 0  # strut axis above the joint


class TopTruss(_Model):
    """Two tubes across the hopper below the top, joined by a vertical web plate."""

    tube_profile: str
    upper_below_top_mm: float = Field(gt=0)  # upper tube axis below the top (z = height)
    depth_mm: float = Field(gt=0)  # between the tube axes
    end_clearance_mm: float = Field(ge=0)  # tube end to the inner wall face
    web_thickness_mm: float = Field(gt=0)
    web_end_inset_mm: float = Field(ge=0)  # web plate ends inside the lower tube ends


class Bracing(_Model):
    """Internal bracing across the hopper, on the inner support column lines or at given positions."""

    at_columns: bool = False
    x_mm: list[float] | None = None
    struts: list[Strut] = []
    top_truss: TopTruss | None = None
    material: str = Field(min_length=1)
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _positions(self) -> Self:
        if self.at_columns == (self.x_mm is not None):
            raise ValueError("bracing: give either at_columns = true or x_mm")
        return self


TierPosition = Literal["bottom", "middle", "top"]


class SpacingRule(_Model):
    """Stiffeners on one wall type in the bottom, middle or top tiers: as few as possible, evenly spaced
    at most `max_spacing_mm` apart between the panel ends and the support column lines."""

    wall: Literal["side", "end"]
    position: TierPosition
    max_spacing_mm: float = Field(gt=0)
    bottom_clearance_mm: float = Field(ge=0)
    top_extension_mm: float
    # Stiffeners under a side bracket stop this far below its bottom (side walls, top tier only).
    stop_under_brackets_mm: float | None = Field(default=None, ge=0)


class StiffeningRules(_Model):
    """Engineering rules for the stiffener layout (spec §30.2, E-02): used for every wall and tier that
    has no explicit layout. Reported as not approved until the engineering owner approves them."""

    standard_profile: str
    column_profile: str | None = None  # on the side walls at the support column lines
    spacing: list[SpacingRule] = Field(min_length=1)
    approved: bool
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> Self:
        keys = [(r.wall, r.position) for r in self.spacing]
        if len(keys) != len(set(keys)):
            raise ValueError("one spacing rule per wall type and tier position")
        return self


class Stiffening(_Model):
    tier_beams: TierBeams | None = None
    top_beams: TopBeams | None = None
    supports: Supports | None = None
    brackets: Brackets | None = None
    bracing: Bracing | None = None
    stiffeners: list[StiffenerLayout] = []  # explicit layouts; they override the rules
    rules: StiffeningRules | None = None


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
        if st.top_beams is not None:
            wanted += [(st.top_beams.side_profile, "channel"), (st.top_beams.end_profile, "channel")]
        if st.supports is not None:
            wanted.append((st.supports.stub_profile, "h_section"))
        if st.rules is not None:
            wanted += [(p, "angle") for p in (st.rules.standard_profile, st.rules.column_profile) if p is not None]
        if st.bracing is not None:
            wanted += [(s.tube_profile, "tube") for s in st.bracing.struts]
            if st.bracing.top_truss is not None:
                wanted.append((st.bracing.top_truss.tube_profile, "tube"))
            if st.bracing.at_columns and st.supports is None:
                errors.append("bracing at_columns needs supports")
            if any(
                s.joint is not None and s.joint >= len(self.parameters.tier_heights_mm.value) for s in st.bracing.struts
            ):
                errors.append("a bracing strut is not at a tier joint")
        for name, kind in wanted:
            if name not in self.profiles or self.profiles[name].kind != kind:
                errors.append(f"profile {name!r} must be a {kind} in [profiles]")
        tiers = len(self.parameters.tier_heights_mm.value)
        if st.brackets is not None and st.supports is None:
            errors.append("brackets need supports")
        if st.brackets is not None and st.brackets.depth_mm >= self.parameters.tier_heights_mm.value[-1]:
            errors.append("the bracket depth must be less than the top tier height")
        if st.tier_beams is not None:
            beams = st.tier_beams
            for wall, values in (("side", beams.side_end_extensions_mm), ("end", beams.end_end_extensions_mm)):
                if values is not None and len(values) != tiers - 1:
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
