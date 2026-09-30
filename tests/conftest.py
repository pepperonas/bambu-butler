"""Shared fixtures: a synthetic Bambu profile tree and a fake Bambu Studio executable.

The fake executable is a test double. It checks the arguments the way the
real CLI does (profile headers, file existence) and writes plausible output,
but it is never presented as a real slice.
"""

from __future__ import annotations

import json
import os
import stat
import struct
import sys
import textwrap
import zipfile
from pathlib import Path

import numpy as np
import pytest


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def box_triangles(sx: float, sy: float, sz: float) -> np.ndarray:
    v = np.array([[0, 0, 0], [sx, 0, 0], [sx, sy, 0], [0, sy, 0],
                  [0, 0, sz], [sx, 0, sz], [sx, sy, sz], [0, sy, sz]], float)
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
         (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]
    return v[np.array(f)]


def write_binary_stl(path: Path, tris: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        fh.write(b"\0" * 80)
        fh.write(struct.pack("<I", len(tris)))
        for tri in tris:
            fh.write(struct.pack("<3f", 0, 0, 0))
            fh.write(tri.astype("<f4").tobytes())
            fh.write(b"\0\0")
    return path


@pytest.fixture
def resources(tmp_path: Path) -> Path:
    """Minimal vendor tree shaped like BambuStudio/resources/profiles/BBL."""
    root = tmp_path / "Bambu Resources"
    bbl = root / "profiles" / "BBL"
    write_json(root / "profiles" / "BBL.json", {"name": "Bambulab", "version": "02.08.00.09"})
    write_json(bbl / "machine" / "fdm_machine_common.json", {
        "type": "machine", "name": "fdm_machine_common", "from": "system", "instantiation": "false",
        "printer_technology": "FFF", "nozzle_diameter": ["0.4"], "printable_height": "250",
        "printable_area": ["0x0", "256x0", "256x256", "0x256"], "min_layer_height": ["0.08"],
        "max_layer_height": ["0.28"], "machine_end_gcode": "",
    })
    write_json(bbl / "machine" / "Mini template end_gcode.json", {
        "name": "Mini template end_gcode", "instantiation": "false", "machine_end_gcode": "G28 ; end",
    })
    write_json(bbl / "machine" / "Bambu Lab A1 mini 0.4 nozzle.json", {
        "type": "machine", "name": "Bambu Lab A1 mini 0.4 nozzle", "inherits": "fdm_machine_common",
        "from": "system", "setting_id": "GM020", "instantiation": "true", "printer_model": "Bambu Lab A1 mini",
        "printable_area": ["0x0", "180x0", "180x180", "0x180"], "printable_height": "180",
        "default_print_profile": "0.20mm Standard @BBL A1M",
        "default_filament_profile": ["Bambu PLA Basic @BBL A1M"],
        "include": ["Mini template end_gcode"],
    })
    write_json(bbl / "machine" / "Bambu Lab X1 Carbon 0.4 nozzle.json", {
        "type": "machine", "name": "Bambu Lab X1 Carbon 0.4 nozzle", "inherits": "fdm_machine_common",
        "from": "system", "instantiation": "true", "printer_model": "Bambu Lab X1 Carbon",
    })
    write_json(bbl / "process" / "fdm_process_common.json", {
        "type": "process", "name": "fdm_process_common", "from": "system", "instantiation": "false",
        "layer_height": "0.2", "wall_loops": "2", "sparse_infill_density": "15%",
        "sparse_infill_pattern": "grid", "enable_support": "0", "support_type": "normal(auto)",
        "outer_wall_speed": ["200"], "seam_position": "aligned", "top_shell_layers": "3",
    })
    write_json(bbl / "process" / "0.20mm Standard @BBL A1M.json", {
        "type": "process", "name": "0.20mm Standard @BBL A1M", "inherits": "fdm_process_common",
        "from": "system", "setting_id": "GP000", "instantiation": "true",
        "compatible_printers": ["Bambu Lab A1 mini 0.4 nozzle"],
    })
    write_json(bbl / "process" / "0.20mm Standard @BBL X1C.json", {
        "type": "process", "name": "0.20mm Standard @BBL X1C", "inherits": "fdm_process_common",
        "from": "system", "instantiation": "true", "compatible_printers": ["Bambu Lab X1 Carbon 0.4 nozzle"],
    })
    write_json(bbl / "filament" / "fdm_filament_pla.json", {
        "type": "filament", "name": "fdm_filament_pla", "from": "system", "instantiation": "false",
        "filament_type": ["PLA"], "nozzle_temperature": ["220"],
    })
    write_json(bbl / "filament" / "Bambu PLA Basic @base.json", {
        "type": "filament", "name": "Bambu PLA Basic @base", "inherits": "fdm_filament_pla",
        "from": "system", "filament_id": "GFA00", "instantiation": "false",
    })
    write_json(bbl / "filament" / "Bambu PLA Basic @BBL A1M.json", {
        "type": "filament", "name": "Bambu PLA Basic @BBL A1M", "inherits": "Bambu PLA Basic @base",
        "from": "system", "setting_id": "GFSA00_02", "instantiation": "true",
        "compatible_printers": ["Bambu Lab A1 mini 0.4 nozzle"],
    })
    write_json(bbl / "filament" / "Bambu PETG Basic @BBL X1C.json", {
        "type": "filament", "name": "Bambu PETG Basic @BBL X1C", "inherits": "fdm_filament_pla",
        "from": "system", "instantiation": "true", "filament_type": ["PETG"],
        "compatible_printers": ["Bambu Lab X1 Carbon 0.4 nozzle"],
    })
    return root


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    root = tmp_path / "Application Support" / "BambuStudio"
    write_json(root / "user" / "12345" / "process" / "My Strong.json", {
        "from": "User", "inherits": "0.20mm Standard @BBL A1M", "name": "My Strong", "wall_loops": "5",
        "version": "2.0.0.0",
    })
    (root / "user" / "12345" / "process" / "My Strong.info").write_text("sync_info = \n")
    write_json(root / "user" / "12345" / "filament" / "Orphan.json", {
        "from": "User", "inherits": "Deleted Parent", "name": "Orphan",
    })
    return root


@pytest.fixture
def workdir(tmp_path: Path) -> Path:
    d = tmp_path / "my prints"
    d.mkdir()
    write_binary_stl(d / "halter mit leerzeichen.stl", box_triangles(40, 20, 30))
    return d


@pytest.fixture
def plan_dict() -> dict:
    return {
        "schema": "bambu-butler/print-plan",
        "schema_version": "1",
        "request": "Stabile Halterung, saubere Oberfläche",
        "model": {"path": "halter mit leerzeichen.stl"},
        "printer": {"profile": "Bambu Lab A1 mini 0.4 nozzle", "nozzle_diameter_mm": 0.4},
        "process": {"profile": "0.20mm Standard @BBL A1M"},
        "filaments": [{"profile": "Bambu PLA Basic @BBL A1M", "material": "PLA"}],
        "settings": {
            "strength": {"wall_loops": 4, "infill_density_percent": 25, "infill_pattern": "gyroid"},
            "support": {"enabled": True, "style": "tree_auto", "build_plate_only": True},
            "quality": {"seam": "back"},
        },
        "output": {"job_name": "halter"},
    }


FAKE_STUDIO = r'''
import json, os, sys, time, zipfile
args = sys.argv[1:]
mode = os.environ.get("FAKE_STUDIO_MODE", "ok")
if "--help" in args:
    print("BambuStudio-02.08.04.57:\nUsage: bambu-studio [ ACTIONS ] [ TRANSFORM ] [ OPTIONS ] [ file.3mf/file.stl ... ]\n")
    for o in ["--export-3mf filename.3mf", "--slice option", "--load-settings \"a.json;b.json\"",
              "--load-filaments \"f.json\"", "--outputdir dir", "--orient", "--arrange option",
              "--scale factor", "--rotate", "--rotate-x", "--rotate-y", "--ensure-on-bed", "--debug level"]:
        print("  " + o)
    sys.exit(0)
with open(os.environ["FAKE_STUDIO_LOG"], "w") as fh:
    json.dump(args, fh)
def opt(name):
    return args[args.index(name) + 1] if name in args else None
outdir = opt("--outputdir")
def result(code, msg):
    with open(os.path.join(outdir, "result.json"), "w") as fh:
        json.dump({"return_code": code, "error_string": msg, "sliced_plates": [
            {"id": 1, "total_predication": 1234.0, "filaments": [{"id": 1, "total_used_g": 9.5}]}] if code == 0 else []}, fh)
    sys.exit(code & 0xFF)
for f in opt("--load-settings").split(";") + opt("--load-filaments").split(";"):
    if not os.path.isfile(f):
        result(-3, "file not found")
    d = json.load(open(f))
    if d.get("from") not in ("system", "User", "user") or d.get("type") not in ("machine", "process", "filament"):
        result(-5, "config error")
if not os.path.isfile(args[-1]):
    result(-3, "model not found")
if mode == "hang":
    time.sleep(60)
if mode == "fail":
    result(-100, "Failed slicing the model.")
target = os.path.join(outdir, opt("--export-3mf"))
with zipfile.ZipFile(target, "w") as z:
    z.writestr("3D/3dmodel.model", "<model/>")
    if "--slice" in args and mode != "nogcode":
        z.writestr("Metadata/plate_1.gcode", "; fake gcode\n")
        z.writestr("Metadata/slice_info.config",
                   '<config><plate><metadata key="index" value="1"/><metadata key="prediction" value="3723"/>'
                   '<metadata key="weight" value="12.34"/><filament id="1" type="PLA" color="#FFFFFF" used_m="4.1" used_g="12.34"/></plate></config>')
result(0, "Success.")
'''


@pytest.fixture
def fake_studio(tmp_path: Path, monkeypatch) -> Path:
    d = tmp_path / "Fake Studio.app dir"
    d.mkdir()
    script = d / "bambu-studio"
    script.write_text(f"#!{sys.executable}\n" + textwrap.dedent(FAKE_STUDIO), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("FAKE_STUDIO_LOG", str(tmp_path / "fake-argv.json"))
    return script


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch, tmp_path):
    for var in ("BAMBU_BUTLER_STUDIO", "BAMBU_BUTLER_RESOURCES", "BAMBU_BUTLER_DATA_DIR",
                "BAMBU_BUTLER_JOBS_DIR", "BAMBU_BUTLER_TIMEOUT", "BAMBU_BUTLER_CONFIG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)
    os.makedirs(tmp_path / "home", exist_ok=True)


def make_3mf(path: Path, *, unit: str = "millimeter", extruders: dict | None = None,
             project: dict | None = None) -> Path:
    tris = box_triangles(10, 10, 10)
    verts = tris.reshape(-1, 3)
    vx = "".join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x, y, z in verts)
    tr = "".join(f'<triangle v1="{3*i}" v2="{3*i+1}" v3="{3*i+2}"/>' for i in range(len(tris)))
    obj_model = (f'<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" unit="{unit}">'
                 f'<resources><object id="1" type="model"><mesh><vertices>{vx}</vertices>'
                 f'<triangles>{tr}</triangles></mesh></object></resources></model>')
    main = ('<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
            'xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06" '
            f'unit="{unit}"><metadata name="Application">BambuStudio-02.08.04.57</metadata><resources>'
            '<object id="2" name="part A" type="model"><components>'
            '<component p:path="/3D/Objects/object_1.model" objectid="1" transform="2 0 0 0 1 0 0 0 1 0 0 0"/>'
            '</components></object>'
            '<object id="3" name="part B" type="model"><components>'
            '<component p:path="/3D/Objects/object_1.model" objectid="1"/></components></object>'
            '</resources><build>'
            '<item objectid="2" transform="1 0 0 0 1 0 0 0 1 50 50 0" printable="1"/>'
            '<item objectid="3" transform="1 0 0 0 1 0 0 0 1 100 50 0" printable="1"/>'
            '</build></model>')
    extruders = extruders or {"2": 1, "3": 2}
    settings = "<config>" + "".join(
        f'<object id="{oid}"><metadata key="name" value="obj{oid}"/><metadata key="extruder" value="{e}"/></object>'
        for oid, e in extruders.items()) + "</config>"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("3D/3dmodel.model", main)
        z.writestr("3D/Objects/object_1.model", obj_model)
        z.writestr("Metadata/model_settings.config", settings)
        z.writestr("Metadata/project_settings.config", json.dumps(project or {
            "printer_settings_id": "Bambu Lab A1 mini 0.4 nozzle",
            "filament_settings_id": ["Bambu PLA Basic @BBL A1M", "Bambu PLA Basic @BBL A1M"],
            "filament_colour": ["#FFFFFF", "#000000"]}))
    return path
