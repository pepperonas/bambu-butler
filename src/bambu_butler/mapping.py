"""Translate plan settings into Bambu Studio profile keys.

Every key and enum value below was checked against
``src/libslic3r/PrintConfig.cpp`` of BambuStudio v02.08.04 (PrintConfigDef and
the ``s_keys_map_*`` enum tables). All of them live in the process profile.
"""

from __future__ import annotations

from typing import Any

from .plan import PrintPlan

VERIFIED_AGAINST = "BambuStudio v02.08.04 (src/libslic3r/PrintConfig.cpp)"

SUPPORT_TYPE = {
    "normal_auto": "normal(auto)",
    "tree_auto": "tree(auto)",
    "normal_manual": "normal(manual)",
    "tree_manual": "tree(manual)",
}
BRIM_TYPE = {
    "auto": "auto_brim",
    "none": "no_brim",
    "outer_only": "outer_only",
    "inner_only": "inner_only",
    "outer_and_inner": "outer_and_inner",
    "ears": "brim_ears",
}
IRONING_TYPE = {"none": "no ironing", "top": "top", "topmost": "topmost", "solid": "solid"}

# plan field path -> (bambu key, kind)
FIELD_MAP: dict[str, tuple[str, str]] = {
    "quality.layer_height_mm": ("layer_height", "float"),
    "quality.first_layer_height_mm": ("initial_layer_print_height", "float"),
    "quality.seam": ("seam_position", "enum"),
    "quality.ironing": ("ironing_type", "enum"),
    "strength.wall_loops": ("wall_loops", "int"),
    "strength.top_layers": ("top_shell_layers", "int"),
    "strength.bottom_layers": ("bottom_shell_layers", "int"),
    "strength.infill_density_percent": ("sparse_infill_density", "percent"),
    "strength.infill_pattern": ("sparse_infill_pattern", "enum"),
    "support.enabled": ("enable_support", "bool"),
    "support.style": ("support_type", "enum"),
    "support.threshold_angle_deg": ("support_threshold_angle", "int"),
    "support.build_plate_only": ("support_on_build_plate_only", "bool"),
    "adhesion.brim": ("brim_type", "enum"),
    "adhesion.brim_width_mm": ("brim_width", "float"),
}
KNOWN_PROCESS_KEYS = frozenset(k for k, _ in FIELD_MAP.values())
ENUM_TRANSLATION = {"support_type": SUPPORT_TYPE, "brim_type": BRIM_TYPE, "ironing_type": IRONING_TYPE}


def _fmt_number(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text or "0"


def encode(kind: str, value: Any) -> str:
    """Encode a value the way Bambu Studio stores it in profile JSON (always strings)."""
    if kind == "bool":
        return "1" if value else "0"
    if kind == "int":
        return str(int(value))
    if kind == "float":
        return _fmt_number(float(value))
    if kind == "percent":
        return _fmt_number(float(value)) + "%"
    return str(value)


def shape_like(base_value: Any, encoded: Any) -> Any:
    """Vector options are stored as lists (one entry per extruder); keep that shape."""
    if isinstance(base_value, list):
        if isinstance(encoded, list):
            return [str(v) for v in encoded]
        return [str(encoded)] * max(1, len(base_value))
    if isinstance(encoded, list):
        return [str(v) for v in encoded]
    if isinstance(encoded, bool):
        return "1" if encoded else "0"
    return str(encoded) if not isinstance(encoded, str) else encoded


def settings_to_process(plan: PrintPlan) -> list[dict[str, Any]]:
    """Return ``[{field, key, value}]`` for every set plan setting."""
    out = []
    groups = plan.settings.model_dump(mode="json")
    for path, (key, kind) in FIELD_MAP.items():
        group, name = path.split(".")
        value = groups[group].get(name)
        if value is None:
            continue
        if key in ENUM_TRANSLATION:
            value = ENUM_TRANSLATION[key][value]
        out.append({"field": f"settings.{path}", "key": key, "value": encode(kind, value)})
    return out
