"""STL and 3MF model inspection.

Only facts that can be read reliably from the file are reported: dimensions,
triangle counts, declared units, objects and metadata, and simple topology
checks. Load direction, ideal orientation or required supports can *not* be
derived from a mesh alone and are intentionally not guessed here.
"""

from __future__ import annotations

import json
import struct
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .errors import ModelFileError

NS_CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
NS_PROD = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
UNIT_TO_MM = {"micron": 0.001, "millimeter": 1.0, "centimeter": 10.0, "inch": 25.4, "foot": 304.8,
              "meter": 1000.0}


@dataclass
class MeshObject:
    name: str
    triangles: np.ndarray  # (n, 3, 3) float64 in millimetres, build transform applied
    object_id: str | None = None
    extruder: int | None = None
    printable: bool = True

    @property
    def triangle_count(self) -> int:
        return int(self.triangles.shape[0])


@dataclass
class ModelInfo:
    path: Path
    format: str
    objects: list[MeshObject]
    unit: str | None = None
    unit_declared: bool = False
    metadata: dict[str, str] = field(default_factory=dict)
    project: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def all_triangles(self) -> np.ndarray:
        if not self.objects:
            return np.zeros((0, 3, 3))
        return np.concatenate([o.triangles for o in self.objects])


# --------------------------------------------------------------------------- STL
def read_stl(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if len(data) < 15:
        raise ModelFileError(f"STL-Datei ist leer oder zu klein: {path}")
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if 84 + count * 50 == len(data):
            record = np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
            arr = np.frombuffer(data, dtype=record, count=count, offset=84)
            return arr["v"].astype(np.float64)
    if data.lstrip()[:5].lower() == b"solid":
        return _read_ascii_stl(data, path)
    raise ModelFileError(f"STL-Datei ist weder gültiges Binär- noch ASCII-STL: {path}")


def _read_ascii_stl(data: bytes, path: Path) -> np.ndarray:
    verts = []
    for line in data.decode("utf-8", errors="replace").splitlines():
        parts = line.strip().split()
        if len(parts) == 4 and parts[0].lower() == "vertex":
            try:
                verts.append([float(parts[1]), float(parts[2]), float(parts[3])])
            except ValueError as exc:
                raise ModelFileError(f"Ungültiger Vertex in ASCII-STL {path}: {line.strip()}") from exc
    if not verts or len(verts) % 3:
        raise ModelFileError(f"ASCII-STL enthält keine vollständigen Dreiecke: {path}")
    return np.asarray(verts, dtype=np.float64).reshape(-1, 3, 3)


# --------------------------------------------------------------------------- 3MF
def _parse_transform(value: str | None) -> np.ndarray:
    m = np.eye(4)
    if not value:
        return m
    nums = [float(x) for x in value.split()]
    if len(nums) != 12:
        raise ModelFileError(f"Ungültige 3MF-Transformation: {value}")
    # 3MF stores the 4x3 matrix row-major, points are row vectors: p' = p * M
    m[:3, :3] = np.array(nums[:9]).reshape(3, 3)
    m[3, :3] = nums[9:]
    return m


def _apply(tris: np.ndarray, m: np.ndarray) -> np.ndarray:
    flat = tris.reshape(-1, 3)
    out = flat @ m[:3, :3] + m[3, :3]
    return out.reshape(-1, 3, 3)


class _ThreeMFReader:
    def __init__(self, zf: zipfile.ZipFile, path: Path):
        self.zf = zf
        self.path = path
        self.docs: dict[str, ET.Element] = {}

    def doc(self, part: str) -> ET.Element:
        part = part.lstrip("/")
        if part not in self.docs:
            try:
                raw = self.zf.read(part)
            except KeyError as exc:
                raise ModelFileError(f"3MF verweist auf fehlenden Teil '{part}': {self.path}") from exc
            try:
                self.docs[part] = ET.fromstring(raw)
            except ET.ParseError as exc:
                raise ModelFileError(f"3MF-Teil '{part}' ist kein gültiges XML: {exc}") from exc
        return self.docs[part]

    def object_triangles(self, part: str, object_id: str, depth: int = 0) -> np.ndarray:
        if depth > 16:
            raise ModelFileError("3MF-Komponenten sind zu tief verschachtelt.")
        root = self.doc(part)
        for obj in root.iter(f"{{{NS_CORE}}}object"):
            if obj.get("id") != object_id:
                continue
            mesh = obj.find(f"{{{NS_CORE}}}mesh")
            if mesh is not None:
                verts = np.array([[float(v.get("x")), float(v.get("y")), float(v.get("z"))]
                                  for v in mesh.iter(f"{{{NS_CORE}}}vertex")], dtype=np.float64)
                idx = np.array([[int(t.get("v1")), int(t.get("v2")), int(t.get("v3"))]
                                for t in mesh.iter(f"{{{NS_CORE}}}triangle")], dtype=np.int64)
                if idx.size == 0:
                    return np.zeros((0, 3, 3))
                return verts[idx]
            parts = []
            comps = obj.find(f"{{{NS_CORE}}}components")
            for comp in (comps if comps is not None else []):
                sub_part = comp.get(f"{{{NS_PROD}}}path") or part
                sub = self.object_triangles(sub_part, comp.get("objectid"), depth + 1)
                parts.append(_apply(sub, _parse_transform(comp.get("transform"))))
            return np.concatenate(parts) if parts else np.zeros((0, 3, 3))
        raise ModelFileError(f"3MF-Objekt {object_id} nicht gefunden in '{part}'.")


def _bambu_object_settings(zf: zipfile.ZipFile) -> dict[str, dict[str, str]]:
    try:
        root = ET.fromstring(zf.read("Metadata/model_settings.config"))
    except (KeyError, ET.ParseError):
        return {}
    out: dict[str, dict[str, str]] = {}
    for obj in root.iter("object"):
        meta = {m.get("key"): m.get("value") for m in obj.findall("metadata") if m.get("key")}
        out[obj.get("id", "")] = meta
    return out


def read_3mf(path: Path) -> ModelInfo:
    try:
        zf = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ModelFileError(f"3MF-Datei ist kein gültiges ZIP-Archiv: {path}") from exc
    with zf:
        reader = _ThreeMFReader(zf, path)
        root = reader.doc("3D/3dmodel.model")
        unit_attr = root.get("unit")
        unit = unit_attr or "millimeter"
        scale = UNIT_TO_MM.get(unit)
        notes: list[str] = []
        if scale is None:
            notes.append(f"Unbekannte 3MF-Einheit '{unit}', es wird Millimeter angenommen.")
            scale = 1.0
        metadata = {m.get("name"): (m.text or "") for m in root.findall(f"{{{NS_CORE}}}metadata")
                    if m.get("name")}
        names = {o.get("id"): o.get("name") for o in root.iter(f"{{{NS_CORE}}}object")}
        settings = _bambu_object_settings(zf)
        objects: list[MeshObject] = []
        build = root.find(f"{{{NS_CORE}}}build")
        for item in (build if build is not None else []):
            oid = item.get("objectid")
            part = item.get(f"{{{NS_PROD}}}path") or "3D/3dmodel.model"
            tris = reader.object_triangles(part, oid)
            tris = _apply(tris, _parse_transform(item.get("transform"))) * scale
            meta = settings.get(oid or "", {})
            extruder = meta.get("extruder")
            objects.append(MeshObject(
                name=meta.get("name") or names.get(oid) or f"object_{oid}",
                triangles=tris,
                object_id=oid,
                extruder=int(extruder) if extruder and extruder.isdigit() else None,
                printable=item.get("printable", "1") != "0",
            ))
        project = _project_summary(zf)
        if not objects:
            notes.append("Die 3MF-Datei enthält keine Build-Objekte.")
        return ModelInfo(path, "3mf", objects, unit=unit, unit_declared=unit_attr is not None,
                         metadata=metadata, project=project, notes=notes)


def _project_summary(zf: zipfile.ZipFile) -> dict:
    names = set(zf.namelist())
    summary: dict = {
        "bambu_project": "Metadata/project_settings.config" in names,
        "has_gcode": any(n.startswith("Metadata/plate_") and n.endswith(".gcode") for n in names),
        "has_slice_info": "Metadata/slice_info.config" in names,
    }
    if summary["bambu_project"]:
        try:
            cfg = json.loads(zf.read("Metadata/project_settings.config"))
        except (ValueError, KeyError):
            cfg = {}
        for key in ("printer_settings_id", "print_settings_id", "filament_settings_id",
                    "filament_colour", "filament_type", "nozzle_diameter", "curr_bed_type"):
            if key in cfg:
                summary[key] = cfg[key]
    return summary


# --------------------------------------------------------------------------- analysis
def load_model(path: Path) -> ModelInfo:
    path = Path(path)
    if not path.is_file():
        raise ModelFileError(f"Modelldatei nicht gefunden: {path}")
    suffix = path.suffix.lower()
    if suffix == ".stl":
        tris = read_stl(path)
        return ModelInfo(path, "stl", [MeshObject(path.stem, tris)], unit=None, unit_declared=False,
                         notes=["STL enthält keine Einheit; Bambu Studio interpretiert Werte als Millimeter."])
    if suffix == ".3mf":
        return read_3mf(path)
    raise ModelFileError(f"Nicht unterstütztes Format '{suffix}'. Unterstützt: .stl, .3mf")


def rotation_matrix(rx: float = 0.0, ry: float = 0.0, rz: float = 0.0) -> np.ndarray:
    """Column-vector rotation applied in the order X, then Y, then Z (degrees)."""
    ax, ay, az = np.radians([rx, ry, rz])
    mx = np.array([[1, 0, 0], [0, np.cos(ax), -np.sin(ax)], [0, np.sin(ax), np.cos(ax)]])
    my = np.array([[np.cos(ay), 0, np.sin(ay)], [0, 1, 0], [-np.sin(ay), 0, np.cos(ay)]])
    mz = np.array([[np.cos(az), -np.sin(az), 0], [np.sin(az), np.cos(az), 0], [0, 0, 1]])
    return mz @ my @ mx


def transformed_size(tris: np.ndarray, rx: float = 0, ry: float = 0, rz: float = 0,
                     scale: float = 1.0) -> list[float]:
    if tris.size == 0:
        return [0.0, 0.0, 0.0]
    pts = tris.reshape(-1, 3) @ rotation_matrix(rx, ry, rz).T * scale
    return [float(v) for v in (pts.max(axis=0) - pts.min(axis=0))]


def topology(tris: np.ndarray, tolerance: float = 1e-5) -> dict:
    """Edge-based checks. Vertices are welded on a grid of ``tolerance`` mm."""
    n = int(tris.shape[0])
    if n == 0:
        return {"triangles": 0}
    e1 = tris[:, 1] - tris[:, 0]
    e2 = tris[:, 2] - tris[:, 0]
    area2 = np.linalg.norm(np.cross(e1, e2), axis=1)
    degenerate = int(np.count_nonzero(area2 < 1e-12))
    keys = np.round(tris.reshape(-1, 3) / tolerance).astype(np.int64)
    _, vid = np.unique(keys, axis=0, return_inverse=True)
    vid = vid.reshape(-1, 3)
    directed = np.concatenate([vid[:, [0, 1]], vid[:, [1, 2]], vid[:, [2, 0]]])
    directed = directed[directed[:, 0] != directed[:, 1]]
    edges = np.sort(directed, axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    open_edges = int(np.count_nonzero(counts == 1))
    nonmanifold = int(np.count_nonzero(counts > 2))
    # In a consistently oriented shell every directed edge occurs once.
    _, directed_counts = np.unique(directed, axis=0, return_counts=True)
    flipped = int(np.count_nonzero(directed_counts > 1))
    volume = float(np.einsum("ij,ij->i", tris[:, 0], np.cross(tris[:, 1], tris[:, 2])).sum() / 6.0)
    return {
        "triangles": n,
        "degenerate_triangles": degenerate,
        "open_edges": open_edges,
        "non_manifold_edges": nonmanifold,
        "inconsistently_oriented_edges": flipped,
        "watertight": open_edges == 0 and nonmanifold == 0,
        "signed_volume_mm3": round(volume, 3),
    }


def analyse(model: ModelInfo, *, bed: tuple[float, float] | None = None,
            height: float | None = None) -> dict:
    tris = model.all_triangles
    report: dict = {
        "path": str(model.path),
        "format": model.format,
        "unit": model.unit or "unbekannt (als mm interpretiert)",
        "unit_declared": model.unit_declared,
        "object_count": len(model.objects),
        "objects": [],
        "metadata": model.metadata,
        "project": model.project,
        "warnings": list(model.notes),
    }
    for obj in model.objects:
        size = transformed_size(obj.triangles)
        entry = {"name": obj.name, "triangles": obj.triangle_count,
                 "size_mm": [round(v, 3) for v in size], "printable": obj.printable}
        if obj.object_id is not None:
            entry["object_id"] = obj.object_id
        if obj.extruder is not None:
            entry["filament_slot"] = obj.extruder
        report["objects"].append(entry)
    if tris.size == 0:
        report["warnings"].append("Modell enthält keine Dreiecke.")
        return report
    mins, maxs = tris.reshape(-1, 3).min(axis=0), tris.reshape(-1, 3).max(axis=0)
    size = maxs - mins
    report["bounding_box_mm"] = {"min": [round(float(v), 3) for v in mins],
                                 "max": [round(float(v), 3) for v in maxs],
                                 "size": [round(float(v), 3) for v in size]}
    topo = topology(tris)
    report["topology"] = topo
    if topo["degenerate_triangles"]:
        report["warnings"].append(f"{topo['degenerate_triangles']} degenerierte Dreiecke (Fläche ~0).")
    if topo["open_edges"]:
        report["warnings"].append(f"{topo['open_edges']} offene Kanten: Mesh ist nicht geschlossen.")
    if topo["non_manifold_edges"]:
        report["warnings"].append(f"{topo['non_manifold_edges']} nicht-mannigfaltige Kanten.")
    if topo["inconsistently_oriented_edges"]:
        report["warnings"].append(f"{topo['inconsistently_oriented_edges']} Kanten mit inkonsistent "
                                  "orientierten Nachbardreiecken (gekippte Normalen).")
    if topo["signed_volume_mm3"] < 0:
        report["warnings"].append("Negatives Volumen: Dreiecksnormalen zeigen vermutlich nach innen.")
    largest = float(size.max())
    if not model.unit_declared:
        if largest < 5:
            report["warnings"].append(
                f"Größte Abmessung nur {largest:.2f} mm - möglicherweise in cm, Zoll oder Metern modelliert.")
        elif largest > 2000:
            report["warnings"].append(
                f"Größte Abmessung {largest:.0f} mm - möglicherweise in Mikrometern modelliert.")
    if bed and height:
        report["fit"] = fit_check(size, bed, height)
    return report


def fit_check(size, bed: tuple[float, float], height: float) -> dict:
    sx, sy, sz = (float(v) for v in size)
    bx, by = bed
    fits_xy = (sx <= bx and sy <= by) or (sy <= bx and sx <= by)
    return {
        "bed_mm": [bx, by, height],
        "model_mm": [round(sx, 3), round(sy, 3), round(sz, 3)],
        "fits": bool(fits_xy and sz <= height),
        "fits_xy": bool(fits_xy),
        "fits_z": bool(sz <= height),
        "note": "Rechteckprüfung ohne Rand/Brim; Ausschlussbereiche des Druckers sind nicht berücksichtigt.",
    }


def bed_from_machine(printable_area: list[str] | None) -> tuple[float, float] | None:
    """Bed size from ``printable_area`` points like ``["0x0","180x0","180x180","0x180"]``."""
    if not printable_area:
        return None
    try:
        pts = [tuple(float(c) for c in p.split("x")) for p in printable_area]
    except ValueError:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (max(xs) - min(xs), max(ys) - min(ys))
