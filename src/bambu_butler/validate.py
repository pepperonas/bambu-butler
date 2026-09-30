"""Plan validation in two explicit stages.

1. ``schema``      - the JSON matches the plan schema (pydantic, ``plan.py``).
2. ``compatible``  - profiles exist, fit together, overrides are known keys,
                     the model loads and fits the printer.

A third stage, ``sliced``, is only ever reported after Bambu Studio actually
produced a sliced project (``slicer.py``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import mesh
from .errors import ButlerError, ProfileError
from .mapping import KNOWN_PROCESS_KEYS, settings_to_process, shape_like
from .plan import PrintPlan, resolve_model_path
from .profiles import ProfileStore, ResolvedProfile


@dataclass
class Issue:
    level: str  # error | warning | info
    code: str
    message: str

    def to_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "message": self.message}


@dataclass
class ValidationResult:
    plan: PrintPlan
    plan_path: Path
    model_path: Path
    issues: list[Issue] = field(default_factory=list)
    printer: ResolvedProfile | None = None
    process: ResolvedProfile | None = None
    filaments: list[ResolvedProfile] = field(default_factory=list)
    process_overrides: dict[str, Any] = field(default_factory=dict)
    filament_overrides: dict[str, Any] = field(default_factory=dict)
    machine_overrides: dict[str, Any] = field(default_factory=dict)
    override_sources: dict[str, str] = field(default_factory=dict)
    model_report: dict | None = None

    def add(self, level: str, code: str, message: str) -> None:
        self.issues.append(Issue(level, code, message))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def compatible(self) -> bool:
        return not self.errors

    @property
    def blocking_questions(self) -> list[str]:
        return [q.question for q in self.plan.open_questions if q.blocking]

    @property
    def status(self) -> str:
        return "compatible" if self.compatible else "schema_valid"

    def to_dict(self) -> dict:
        return {
            "stages": {
                "schema_valid": True,
                "compatible_with_profiles": self.compatible,
                "sliced": False,
            },
            "status": self.status,
            "blocking_questions": self.blocking_questions,
            "issues": [i.to_dict() for i in self.issues],
            "profiles": {
                "printer": self.printer.name if self.printer else None,
                "printer_system_name": self.printer.system_name if self.printer else None,
                "process": self.process.name if self.process else None,
                "filaments": [f.name for f in self.filaments],
            },
            "overrides": {
                "process": self.process_overrides,
                "filament": self.filament_overrides,
                "machine": self.machine_overrides,
            },
            "model": self.model_report,
        }


def _resolve(store: ProfileStore, name: str, ptype: str, result: ValidationResult) -> ResolvedProfile | None:
    try:
        record = store.find(name, ptype=ptype)
        resolved = store.resolve(record)
    except ButlerError as exc:
        result.add("error", exc.code, exc.message)
        return None
    if not record.instantiable:
        result.add("error", "profile_not_instantiable",
                   f"'{name}' ist ein Basisprofil und kann nicht direkt verwendet werden.")
    for w in resolved.warnings:
        result.add("warning", "profile_warning", w)
    return resolved


def _floats(value: Any) -> list[float]:
    values = value if isinstance(value, list) else [value]
    out = []
    for v in values:
        try:
            out.append(float(str(v).rstrip("%")))
        except (TypeError, ValueError):
            continue
    return out


def validate_plan(plan: PrintPlan, plan_path: Path, store: ProfileStore) -> ValidationResult:
    model_path = resolve_model_path(plan, plan_path)
    result = ValidationResult(plan, plan_path, model_path)

    # ---- profiles
    printer = _resolve(store, plan.printer.profile, "machine", result)
    process = _resolve(store, plan.process.profile, "process", result)
    filaments = [_resolve(store, f.profile, "filament", result) for f in plan.filaments]
    result.printer, result.process = printer, process
    result.filaments = [f for f in filaments if f]

    if printer:
        nozzles = _floats(printer.get("nozzle_diameter"))
        expected = plan.printer.nozzle_diameter_mm
        if expected is not None and nozzles and all(abs(n - expected) > 1e-6 for n in nozzles):
            result.add("error", "nozzle_mismatch",
                       f"Plan erwartet Düse {expected} mm, Profil '{printer.name}' hat {nozzles}.")
        if printer.system_name is None:
            result.add("error", "printer_without_system_parent",
                       f"Druckerprofil '{printer.name}' basiert auf keinem Systemprofil.")
        extruders = len(nozzles) or 1
        if len(plan.filaments) > extruders:
            result.add("warning", "multi_filament",
                       f"{len(plan.filaments)} Filamente bei {extruders} Extruder(n): benötigt AMS/Filamentwechsel. "
                       "Ob ein AMS vorhanden ist, kann Bambu Butler nicht prüfen.")

    for label, profile in [("Prozess", process), *[("Filament", f) for f in result.filaments]]:
        if printer and profile:
            ok, reason = store.compatibility(profile, printer)
            if ok is False:
                result.add("error", "incompatible_profile", f"{label}: {reason}")
            elif ok is None:
                result.add("warning", "compatibility_unknown", f"{label} '{profile.name}': {reason}")

    for selection, profile in zip(plan.filaments, filaments, strict=True):
        if profile and selection.material:
            actual = [str(v).upper() for v in (profile.get("filament_type") or [])] if isinstance(
                profile.get("filament_type"), list) else [str(profile.get("filament_type") or "").upper()]
            if selection.material.upper() not in actual:
                result.add("error", "material_mismatch",
                           f"Filament '{profile.name}' ist {actual}, Plan erwartet {selection.material}.")

    # ---- overrides
    if process:
        mapped = settings_to_process(plan)
        for item in mapped:
            base = process.get(item["key"])
            result.process_overrides[item["key"]] = shape_like(base, item["value"])
            result.override_sources[f"process.{item['key']}"] = item["field"]
        for key, value in plan.overrides.process.items():
            if key in result.process_overrides:
                result.add("error", "override_conflict",
                           f"'{key}' ist sowohl über settings als auch overrides.process gesetzt.")
                continue
            if key not in process.values and key not in KNOWN_PROCESS_KEYS:
                result.add("error", "unknown_key",
                           f"Unbekannter Prozessschlüssel '{key}' (nicht im Basisprofil '{process.name}').")
                continue
            result.process_overrides[key] = shape_like(process.get(key), value)
            result.override_sources[f"process.{key}"] = "overrides.process"
    for scope, profile, target in [("filament", result.filaments[0] if result.filaments else None,
                                    result.filament_overrides),
                                   ("machine", printer, result.machine_overrides)]:
        raw = getattr(plan.overrides, scope)
        if not raw or profile is None:
            continue
        for key, value in raw.items():
            if key not in profile.values:
                result.add("error", "unknown_key",
                           f"Unbekannter {scope}-Schlüssel '{key}' (nicht im Basisprofil '{profile.name}').")
                continue
            target[key] = shape_like(profile.get(key), value)
            result.override_sources[f"{scope}.{key}"] = f"overrides.{scope}"
    if len(result.filaments) > 1 and plan.overrides.filament:
        result.add("info", "filament_overrides_scope",
                   "overrides.filament wird auf alle Filamentprofile angewendet.")

    # ---- layer height limits from the machine profile
    if printer and process:
        lh = _floats(result.process_overrides.get("layer_height", process.get("layer_height")))
        lo = _floats(printer.get("min_layer_height"))
        hi = _floats(printer.get("max_layer_height"))
        if lh and lo and lh[0] < min(lo) - 1e-9:
            result.add("error", "layer_height_out_of_range",
                       f"Schichthöhe {lh[0]} mm liegt unter dem Druckerminimum {min(lo)} mm.")
        if lh and hi and lh[0] > max(hi) + 1e-9:
            result.add("error", "layer_height_out_of_range",
                       f"Schichthöhe {lh[0]} mm liegt über dem Druckermaximum {max(hi)} mm.")

    s = plan.settings.support
    if s.enabled is False and (s.style or s.threshold_angle_deg):
        result.add("info", "support_disabled", "Support ist deaktiviert; weitere Support-Werte wirken nicht.")

    # ---- model
    _check_model(plan, result, printer)
    for question in result.blocking_questions:
        result.add("warning", "blocking_question", f"Offene Frage blockiert das Slicen: {question}")
    return result


def _check_model(plan: PrintPlan, result: ValidationResult, printer: ResolvedProfile | None) -> None:
    try:
        model = mesh.load_model(result.model_path)
    except ButlerError as exc:
        result.add("error", exc.code, exc.message)
        return
    bed = mesh.bed_from_machine(printer.get("printable_area")) if printer else None
    height = _floats(printer.get("printable_height"))[0] if printer and printer.get("printable_height") else None
    report = mesh.analyse(model)
    t = plan.transform
    size = mesh.transformed_size(model.all_triangles, t.rotate_x_deg, t.rotate_y_deg, t.rotate_z_deg, t.scale)
    report["size_after_transform_mm"] = [round(v, 3) for v in size]
    if bed and height:
        fit = mesh.fit_check(size, bed, height)
        report["fit"] = fit
        if not fit["fits"]:
            level = "warning" if t.auto_orient else "error"
            result.add(level, "model_too_large",
                       f"Modell {fit['model_mm']} mm passt nicht in den Druckraum {fit['bed_mm']} mm.")
    for w in report.get("warnings", []):
        result.add("warning", "model_warning", w)
    if model.format == "3mf":
        project = model.project
        project_filaments = project.get("filament_settings_id")
        if isinstance(project_filaments, list) and len(project_filaments) != len(plan.filaments):
            result.add("warning", "filament_count_changes",
                       f"Das 3MF nutzt {len(project_filaments)} Filamente, der Plan {len(plan.filaments)}. "
                       "Die Bambu-CLI ersetzt die Filamentliste; Zuordnungen können sich ändern.")
        used_slots = {o.extruder for o in model.objects if o.extruder}
        too_high = sorted(s for s in used_slots if s > len(plan.filaments))
        if too_high:
            result.add("error", "filament_slot_missing",
                       f"Objekte nutzen Filament-Slot(s) {too_high}, der Plan definiert nur "
                       f"{len(plan.filaments)} Filament(e).")
        if project.get("has_gcode"):
            result.add("info", "already_sliced", "Das Eingabe-3MF enthält bereits G-Code; er wird neu erzeugt.")
    result.model_report = report


def require_ready(result: ValidationResult, *, allow_open_questions: bool = False) -> None:
    if result.errors:
        raise ProfileError("Plan ist nicht mit den vorhandenen Profilen kompatibel: "
                           + "; ".join(i.message for i in result.errors[:5]),
                           details={"issues": [i.to_dict() for i in result.issues]})
    if result.blocking_questions and not allow_open_questions:
        raise ButlerError("Der Plan enthält blockierende offene Fragen: " + "; ".join(result.blocking_questions),
                          hint="Fragen klären und aus open_questions entfernen oder blocking=false setzen.")
