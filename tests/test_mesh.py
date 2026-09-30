import numpy as np
import pytest

from bambu_butler import mesh
from bambu_butler.errors import ModelFileError

from .conftest import box_triangles, make_3mf, write_binary_stl


def test_binary_stl(workdir):
    info = mesh.load_model(workdir / "halter mit leerzeichen.stl")
    report = mesh.analyse(info, bed=(180, 180), height=180)
    assert report["bounding_box_mm"]["size"] == [40, 20, 30]
    assert report["topology"]["watertight"]
    assert report["topology"]["signed_volume_mm3"] == pytest.approx(40 * 20 * 30)
    assert report["fit"]["fits"]


def test_ascii_stl(tmp_path):
    tris = box_triangles(1, 2, 3)
    lines = ["solid t"]
    for t in tris:
        lines += ["facet normal 0 0 0", "outer loop"] + [f"vertex {x} {y} {z}" for x, y, z in t]
        lines += ["endloop", "endfacet"]
    lines.append("endsolid t")
    p = tmp_path / "a.stl"
    p.write_text("\n".join(lines))
    info = mesh.load_model(p)
    report = mesh.analyse(info)
    assert report["bounding_box_mm"]["size"] == [1, 2, 3]
    assert any("cm, Zoll" in w for w in report["warnings"])


def test_open_mesh_detected(tmp_path):
    p = write_binary_stl(tmp_path / "open.stl", box_triangles(10, 10, 10)[:-2])
    topo = mesh.analyse(mesh.load_model(p))["topology"]
    assert not topo["watertight"] and topo["open_edges"] > 0


def test_invalid_files(tmp_path):
    (tmp_path / "x.stl").write_bytes(b"garbage-data-xx")
    with pytest.raises(ModelFileError):
        mesh.load_model(tmp_path / "x.stl")
    (tmp_path / "x.3mf").write_bytes(b"not a zip")
    with pytest.raises(ModelFileError):
        mesh.load_model(tmp_path / "x.3mf")
    (tmp_path / "x.obj").write_text("v 0 0 0")
    with pytest.raises(ModelFileError):
        mesh.load_model(tmp_path / "x.obj")


def test_3mf_components_transforms_and_metadata(tmp_path):
    info = mesh.load_model(make_3mf(tmp_path / "p.3mf"))
    assert [o.name for o in info.objects] == ["obj2", "obj3"]
    assert [o.extruder for o in info.objects] == [1, 2]
    a = mesh.transformed_size(info.objects[0].triangles)
    assert a == pytest.approx([20, 10, 10])  # component scaled x2 in X
    report = mesh.analyse(info)
    assert report["bounding_box_mm"]["min"] == [50, 50, 0]
    assert report["metadata"]["Application"].startswith("BambuStudio")
    assert report["project"]["filament_settings_id"][0] == "Bambu PLA Basic @BBL A1M"


def test_3mf_units(tmp_path):
    info = mesh.load_model(make_3mf(tmp_path / "cm.3mf", unit="centimeter"))
    assert info.unit == "centimeter" and info.unit_declared
    assert mesh.transformed_size(info.objects[1].triangles) == pytest.approx([100, 100, 100])


def test_rotation_matrix():
    tris = box_triangles(10, 20, 30)
    assert mesh.transformed_size(tris, rx=90) == pytest.approx([10, 30, 20])
    assert mesh.transformed_size(tris, rz=90, scale=2) == pytest.approx([40, 20, 60])
    assert np.allclose(mesh.rotation_matrix(), np.eye(3))


def test_bed_from_machine():
    assert mesh.bed_from_machine(["0x0", "180x0", "180x180", "0x180"]) == (180, 180)
    assert mesh.bed_from_machine(None) is None


def test_flipped_triangles_detected(tmp_path):
    tris = box_triangles(10, 10, 10).copy()
    tris[0] = tris[0][[0, 2, 1]]
    report = mesh.analyse(mesh.load_model(write_binary_stl(tmp_path / "f.stl", tris)))
    assert report["topology"]["inconsistently_oriented_edges"] > 0
    assert any("gekippte Normalen" in w for w in report["warnings"])
