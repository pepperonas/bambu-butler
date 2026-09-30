"""Bambu Studio CLI invocation and result parsing.

Flags and exit codes are taken from BambuStudio v02.08 sources:
``src/libslic3r/PrintConfig.cpp`` (CLI option definitions, underscores become
dashes), ``src/libslic3r/Utils.hpp`` (CLI_* return codes) and
``src/BambuStudio.cpp`` (``result.json`` written to ``--outputdir``).
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from .errors import UnsafeArgumentError

CLI_ERRORS: dict[int, tuple[str, str]] = {
    0: ("CLI_SUCCESS", "Erfolgreich."),
    -1: ("CLI_ENVIRONMENT_ERROR", "Umgebung konnte nicht eingerichtet werden."),
    -2: ("CLI_INVALID_PARAMS", "Ungültige Parameter für den Slicer."),
    -3: ("CLI_FILE_NOTFOUND", "Eingabedateien wurden nicht gefunden."),
    -4: ("CLI_FILELIST_INVALID_ORDER", "Ungültige Dateireihenfolge (3MF muss zuerst stehen)."),
    -5: ("CLI_CONFIG_FILE_ERROR", "Profildatei ist ungültig und kann nicht gelesen werden."),
    -6: ("CLI_DATA_FILE_ERROR", "Modelldatei kann nicht gelesen werden."),
    -7: ("CLI_INVALID_PRINTER_TECH", "Nicht unterstützte Druckertechnik (kein FDM)."),
    -8: ("CLI_UNSUPPORTED_OPERATION", "Nicht unterstützte CLI-Anweisung."),
    -9: ("CLI_COPY_OBJECTS_ERROR", "Objekte konnten nicht kopiert werden."),
    -10: ("CLI_SCALE_TO_FIT_ERROR", "Skalieren auf die Platte fehlgeschlagen."),
    -11: ("CLI_EXPORT_STL_ERROR", "STL-Export fehlgeschlagen."),
    -12: ("CLI_EXPORT_OBJ_ERROR", "OBJ-Export fehlgeschlagen."),
    -13: ("CLI_EXPORT_3MF_ERROR", "3MF-Export fehlgeschlagen."),
    -14: ("CLI_OUT_OF_MEMORY", "Speicher beim Slicen erschöpft."),
    -15: ("CLI_3MF_NOT_SUPPORT_MACHINE_CHANGE", "Der gewählte Drucker wird nicht unterstützt."),
    -16: ("CLI_3MF_NEW_MACHINE_NOT_SUPPORTED", "Der gewählte Drucker ist nicht mit dem 3MF kompatibel."),
    -17: ("CLI_PROCESS_NOT_COMPATIBLE", "Drucker ist nicht mit dem Prozessprofil kompatibel."),
    -18: ("CLI_INVALID_VALUES_IN_3MF", "Ungültige Parameterwerte im 3MF."),
    -19: ("CLI_POSTPROCESS_NOT_SUPPORTED", "Post-Processing wird in der CLI nicht unterstützt."),
    -20: ("CLI_PRINTABLE_SIZE_REDUCED", "Druckbett des Druckers ist kleiner als im Profil."),
    -21: ("CLI_OBJECT_ARRANGE_FAILED", "Automatisches Anordnen fehlgeschlagen."),
    -22: ("CLI_OBJECT_ORIENT_FAILED", "Automatisches Ausrichten fehlgeschlagen."),
    -23: ("CLI_MODIFIED_PARAMS_TO_PRINTER", "Druckbereich/-höhe/Ausschlussbereich dürfen nicht geändert werden."),
    -24: ("CLI_FILE_VERSION_NOT_SUPPORTED", "Nicht unterstützte 3MF-Version."),
    -25: ("CLI_3MF_FEATURE_NOT_SUPPORTED", "3MF enthält nicht unterstützte Funktionen."),
    -50: ("CLI_NO_SUITABLE_OBJECTS", "Platte leer oder kein Objekt vollständig auf der Platte."),
    -51: ("CLI_VALIDATE_ERROR", "Fehlerhafte Slicing-Parameter."),
    -52: ("CLI_OBJECTS_PARTLY_INSIDE", "Objekte ragen über den Rand des Druckbetts."),
    -58: ("CLI_SLICING_TIME_EXCEEDS_LIMIT", "Slicing-Zeitlimit überschritten."),
    -59: ("CLI_TRIANGLE_COUNT_EXCEEDS_LIMIT", "Zu viele Dreiecke auf einer Platte."),
    -60: ("CLI_NO_SUITABLE_OBJECTS_AFTER_SKIP", "Keine druckbaren Objekte nach dem Überspringen."),
    -61: ("CLI_FILAMENT_NOT_MATCH_BED_TYPE", "Filament passt nicht zum Plattentyp."),
    -62: ("CLI_FILAMENTS_DIFFERENT_TEMP", "Temperaturunterschied der Filamente zu groß."),
    -63: ("CLI_OBJECT_COLLISION_IN_SEQ_PRINT", "Objektkollision im Objekt-für-Objekt-Modus."),
    -64: ("CLI_OBJECT_COLLISION_IN_LAYER_PRINT", "Objektkollision erkannt."),
    -65: ("CLI_SPIRAL_MODE_INVALID_PARAMS", "Parameter sind nicht mit dem Vasenmodus vereinbar."),
    -66: ("CLI_FILAMENT_CAN_NOT_MAP", "Filamente können keinem Extruder zugeordnet werden."),
    -67: ("CLI_ONLY_ONE_TPU_SUPPORTED", "Nur ein TPU-Filament wird unterstützt."),
    -68: ("CLI_FILAMENTS_NOT_SUPPORTED_BY_EXTRUDER", "Filament auf zugeordnetem Extruder nicht druckbar."),
    -100: ("CLI_SLICING_ERROR", "Slicen des Modells fehlgeschlagen."),
    -101: ("CLI_GCODE_PATH_CONFLICTS", "G-Code-Pfadkonflikte nach dem Slicen."),
    -102: ("CLI_GCODE_PATH_IN_UNPRINTABLE_AREA", "G-Code im nicht druckbaren Bereich."),
    -103: ("CLI_FILAMENT_UNPRINTABLE_ON_FIRST_LAYER", "Filament auf der ersten Schicht nicht druckbar."),
    -104: ("CLI_GCODE_PATH_OUTSIDE", "G-Code außerhalb des Druckbereichs (Support, Brim, Skirt?)."),
    -105: ("CLI_GCODE_IN_WRAPPING_DETECT_AREA", "G-Code im Wrapping-Erkennungsbereich."),
}


def describe_exit(code: int | None) -> dict:
    if code is None:
        return {"code": None, "name": None, "message": "Kein Rückgabewert (Zeitüberschreitung)."}
    # Exit codes are negative in the sources; POSIX reports them modulo 256.
    signed = code - 256 if code > 127 else code
    name, message = CLI_ERRORS.get(signed, ("UNKNOWN", f"Unbekannter Rückgabewert {signed}."))
    return {"code": signed, "name": name, "message": message}


def _check_list_path(path: Path) -> str:
    text = str(path)
    if ";" in text or '"' in text:
        raise UnsafeArgumentError(
            f"Pfad enthält ';' oder '\"' und kann nicht sicher an --load-settings übergeben werden: {text}",
            hint="Jobs-Verzeichnis ohne diese Zeichen wählen.")
    return text


def build_command(executable: Path, *, model: Path, machine: Path, process: Path, filaments: list[Path],
                  outputdir: Path, export_name: str, slice_plates: bool, transform, debug_level: int = 2
                  ) -> list[str]:
    """Build the argument vector. Paths may contain spaces; nothing is shell-quoted."""
    if "/" in export_name or "\\" in export_name:
        raise UnsafeArgumentError("export_name darf keinen Pfadtrenner enthalten.")
    argv: list[str] = [str(executable)]
    if transform.rotate_x_deg:
        argv += ["--rotate-x", _num(transform.rotate_x_deg)]
    if transform.rotate_y_deg:
        argv += ["--rotate-y", _num(transform.rotate_y_deg)]
    if transform.rotate_z_deg:
        argv += ["--rotate", _num(transform.rotate_z_deg)]
    if transform.scale != 1.0:
        argv += ["--scale", _num(transform.scale)]
    if transform.rotate_x_deg or transform.rotate_y_deg:
        argv += ["--ensure-on-bed"]
    argv += ["--orient", "1" if transform.auto_orient else "0"]
    argv += ["--arrange", "1" if transform.arrange else "0"]
    argv += ["--load-settings", ";".join([_check_list_path(machine), _check_list_path(process)])]
    argv += ["--load-filaments", ";".join(_check_list_path(f) for f in filaments)]
    if slice_plates:
        argv += ["--slice", "0"]
    argv += ["--export-3mf", export_name]
    argv += ["--outputdir", str(outputdir)]
    argv += ["--debug", str(debug_level)]
    model_arg = str(model)
    if model_arg.startswith("-"):
        raise UnsafeArgumentError("Modellpfad darf nicht mit '-' beginnen; absoluten Pfad verwenden.")
    argv.append(model_arg)
    return argv


def _num(value: float) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".")


def read_result_json(outputdir: Path) -> dict | None:
    path = outputdir / "result.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def read_slice_info(project: Path) -> dict | None:
    """Parse ``Metadata/slice_info.config`` from a sliced 3MF (real slicer output only)."""
    if not project.is_file():
        return None
    try:
        with zipfile.ZipFile(project) as zf:
            names = set(zf.namelist())
            if "Metadata/slice_info.config" not in names:
                return None
            root = ET.fromstring(zf.read("Metadata/slice_info.config"))
            gcode_files = sorted(n for n in names if n.startswith("Metadata/plate_") and n.endswith(".gcode"))
    except (zipfile.BadZipFile, ET.ParseError, KeyError):
        return None
    plates = []
    for plate in root.iter("plate"):
        meta = {m.get("key"): m.get("value") for m in plate.findall("metadata")}
        filaments = [{k: f.get(k) for k in ("id", "type", "color", "used_m", "used_g") if f.get(k) is not None}
                     for f in plate.findall("filament")]
        warnings = [w.get("msg") for w in plate.findall("warning") if w.get("msg")]
        plates.append({
            "index": meta.get("index"),
            "prediction_seconds": _to_float(meta.get("prediction")),
            "weight_g": _to_float(meta.get("weight")),
            "support_used": meta.get("support_used"),
            "filaments": filaments,
            "warnings": warnings,
        })
    return {"plates": plates, "gcode_files": gcode_files}


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def summarize_slice(result_json: dict | None, slice_info: dict | None) -> dict | None:
    """Print time and material taken only from real slicer output."""
    if slice_info and slice_info.get("plates") and slice_info.get("gcode_files"):
        plates = slice_info["plates"]
        seconds = [p["prediction_seconds"] for p in plates if p["prediction_seconds"] is not None]
        grams = [p["weight_g"] for p in plates if p["weight_g"] is not None]
        return {
            "source": "3MF Metadata/slice_info.config",
            "print_time_seconds": sum(seconds) if seconds else None,
            "filament_g": round(sum(grams), 2) if grams else None,
            "plates": plates,
        }
    if result_json and result_json.get("sliced_plates"):
        plates = result_json["sliced_plates"]
        seconds = [p.get("total_predication") for p in plates if p.get("total_predication") is not None]
        grams = [sum(f.get("total_used_g", 0) for f in p.get("filaments", [])) for p in plates]
        return {
            "source": "result.json",
            "print_time_seconds": sum(seconds) if seconds else None,
            "filament_g": round(sum(grams), 2) if grams else None,
            "plates": plates,
        }
    return None


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unbekannt"
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h} h {m:02d} min" if h else f"{m} min {s:02d} s"
