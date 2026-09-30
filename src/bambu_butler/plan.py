"""Versioned print plan schema (``bambu-butler/print-plan`` v1).

The plan is Bambu Butler's own stable format. Claude Code writes it; Bambu
Butler validates it and translates it into verified Bambu Studio fields
(``mapping.py``). Field names here must not change within a schema version.
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from .errors import PlanError

SCHEMA_ID = "https://github.com/pepperonas/bambu-butler/schemas/print-plan.v1.schema.json"
SCHEMA_VERSION = "1"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModelInput(_Strict):
    path: str = Field(description="Path to the .stl or .3mf file, relative to the plan file or absolute.")

    @field_validator("path")
    @classmethod
    def _suffix(cls, v: str) -> str:
        if Path(v).suffix.lower() not in (".stl", ".3mf"):
            raise ValueError("Nur .stl und .3mf werden unterstützt.")
        return v


class PrinterSelection(_Strict):
    profile: str = Field(description="Exact name of a machine profile as listed by 'profiles list'.")
    nozzle_diameter_mm: float | None = Field(
        default=None, gt=0, le=2,
        description="Expected nozzle diameter. Checked against the machine profile, not used to pick it.")


class ProcessSelection(_Strict):
    profile: str = Field(description="Exact name of a process profile compatible with the printer.")


class FilamentSelection(_Strict):
    profile: str = Field(description="Exact name of a filament profile compatible with the printer.")
    material: str | None = Field(
        default=None, description="Expected filament_type, e.g. 'PLA'. Checked against the profile.")


class Seam(str, Enum):
    nearest = "nearest"
    aligned = "aligned"
    back = "back"
    random = "random"


class Ironing(str, Enum):
    none = "none"
    top = "top"
    topmost = "topmost"
    solid = "solid"


class InfillPattern(str, Enum):
    concentric = "concentric"
    zig_zag = "zig-zag"
    grid = "grid"
    line = "line"
    cubic = "cubic"
    triangles = "triangles"
    tri_hexagon = "tri-hexagon"
    gyroid = "gyroid"
    honeycomb = "honeycomb"
    adaptivecubic = "adaptivecubic"
    alignedrectilinear = "alignedrectilinear"
    honeycomb_3d = "3dhoneycomb"
    hilbertcurve = "hilbertcurve"
    archimedeanchords = "archimedeanchords"
    octagramspiral = "octagramspiral"
    supportcubic = "supportcubic"
    lightning = "lightning"
    crosshatch = "crosshatch"


class SupportStyle(str, Enum):
    normal_auto = "normal_auto"
    tree_auto = "tree_auto"
    normal_manual = "normal_manual"
    tree_manual = "tree_manual"


class Brim(str, Enum):
    auto = "auto"
    none = "none"
    outer_only = "outer_only"
    inner_only = "inner_only"
    outer_and_inner = "outer_and_inner"
    ears = "ears"


class Quality(_Strict):
    layer_height_mm: float | None = Field(default=None, gt=0, le=1.0)
    first_layer_height_mm: float | None = Field(default=None, gt=0, le=1.0)
    seam: Seam | None = None
    ironing: Ironing | None = None


class Strength(_Strict):
    wall_loops: int | None = Field(default=None, ge=0, le=1000)
    top_layers: int | None = Field(default=None, ge=0, le=1000)
    bottom_layers: int | None = Field(default=None, ge=0, le=1000)
    infill_density_percent: float | None = Field(default=None, ge=0, le=100)
    infill_pattern: InfillPattern | None = None


class Support(_Strict):
    enabled: bool | None = None
    style: SupportStyle | None = None
    threshold_angle_deg: int | None = Field(default=None, ge=1, le=90)
    build_plate_only: bool | None = None


class Adhesion(_Strict):
    brim: Brim | None = None
    brim_width_mm: float | None = Field(default=None, ge=0, le=100)


class Settings(_Strict):
    quality: Quality = Field(default_factory=Quality)
    strength: Strength = Field(default_factory=Strength)
    support: Support = Field(default_factory=Support)
    adhesion: Adhesion = Field(default_factory=Adhesion)


class RawOverrides(_Strict):
    """Direct Bambu Studio keys. Each key must exist in the resolved base profile."""

    process: dict[str, Any] = Field(default_factory=dict)
    filament: dict[str, Any] = Field(default_factory=dict)
    machine: dict[str, Any] = Field(default_factory=dict)


class Transform(_Strict):
    rotate_x_deg: float = 0.0
    rotate_y_deg: float = 0.0
    rotate_z_deg: float = 0.0
    scale: float = Field(default=1.0, gt=0, le=100)
    auto_orient: bool = Field(default=False, description="Let Bambu Studio auto-orient (--orient 1).")
    arrange: bool = Field(default=True, description="Let Bambu Studio arrange on the plate (--arrange 1).")


class Output(_Strict):
    directory: str | None = Field(default=None, description="Jobs directory. Default: settings jobs_dir.")
    job_name: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")


class Note(_Strict):
    text: str = Field(min_length=1)
    reason: str | None = None


class Rationale(_Strict):
    setting: str = Field(min_length=1)
    value: Any = None
    reason: str = Field(min_length=1)


class OpenQuestion(_Strict):
    question: str = Field(min_length=1)
    blocking: bool = Field(default=False, description="True if slicing must wait for an answer.")


class PrintPlan(_Strict):
    model_config = ConfigDict(extra="forbid", title="Bambu Butler print plan v1")

    schema_: Literal["bambu-butler/print-plan"] = Field(alias="schema", default="bambu-butler/print-plan")
    schema_version: Literal["1"] = SCHEMA_VERSION
    comment: str | None = Field(default=None, alias="$comment", description="Free text, ignored.")
    request: str | None = Field(default=None, description="The original natural-language request.")
    model: ModelInput
    printer: PrinterSelection
    process: ProcessSelection
    filaments: list[FilamentSelection] = Field(min_length=1, max_length=32)
    settings: Settings = Field(default_factory=Settings)
    overrides: RawOverrides = Field(default_factory=RawOverrides)
    transform: Transform = Field(default_factory=Transform)
    output: Output = Field(default_factory=Output)
    assumptions: list[Note] = Field(default_factory=list)
    rationale: list[Rationale] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)

    @model_validator(mode="after")
    def _machine_overrides(self) -> PrintPlan:
        from .profiles import LOCKED_MACHINE_KEYS

        locked = sorted(set(self.overrides.machine) & LOCKED_MACHINE_KEYS)
        if locked:
            raise ValueError("Diese Druckerwerte lehnt die Bambu-CLI ab und dürfen nicht überschrieben "
                             "werden: " + ", ".join(locked))
        return self


def json_schema() -> dict:
    schema = PrintPlan.model_json_schema(by_alias=True)
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": SCHEMA_ID, **schema}
    return schema



def load_plan(path: Path) -> PrintPlan:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PlanError(f"Druckplan nicht gefunden: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PlanError(f"Druckplan ist kein gültiges JSON: {exc}") from exc
    return parse_plan(raw)


def parse_plan(raw: Any) -> PrintPlan:
    try:
        return PrintPlan.model_validate(raw)
    except ValidationError as exc:
        issues = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"])
            issues.append({"location": loc, "message": err["msg"]})
        text = "; ".join(f"{i['location']}: {i['message']}" for i in issues[:8])
        raise PlanError(f"Druckplan entspricht nicht dem Schema v1: {text}",
                        details={"issues": issues}) from exc


def resolve_model_path(plan: PrintPlan, plan_path: Path) -> Path:
    p = Path(plan.model.path).expanduser()
    return p if p.is_absolute() else (plan_path.parent / p).resolve()
