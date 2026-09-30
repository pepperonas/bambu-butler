import pytest

from bambu_butler.errors import InheritanceCycleError, ProfileError, ProfileNotFoundError
from bambu_butler.profiles import ProfileStore, diff_values, export_for_cli

from .conftest import write_json


def test_resolves_inheritance_and_includes(resources):
    store = ProfileStore.load(resources, None)
    m = store.resolve("Bambu Lab A1 mini 0.4 nozzle", ptype="machine")
    assert m.chain == ["fdm_machine_common", "Bambu Lab A1 mini 0.4 nozzle"]
    assert m.get("printable_height") == "180"  # child overrides parent
    assert m.get("min_layer_height") == ["0.08"]  # inherited
    assert m.get("machine_end_gcode") == "G28 ; end"  # from include
    assert "include" not in m.values and "inherits" not in m.values
    assert m.system_name == "Bambu Lab A1 mini 0.4 nozzle"


def test_filament_id_is_inherited(resources):
    store = ProfileStore.load(resources, None)
    f = store.resolve("Bambu PLA Basic @BBL A1M")
    assert f.filament_id == "GFA00"
    assert f.get("filament_type") == ["PLA"]


def test_user_profile_inherits_system(resources, data_dir):
    store = ProfileStore.load(resources, data_dir)
    p = store.resolve("My Strong", ptype="process")
    assert p.record.origin == "user"
    assert p.get("wall_loops") == "5"
    assert p.get("layer_height") == "0.2"
    assert p.system_name == "0.20mm Standard @BBL A1M"
    assert p.compatible_printers() == ["Bambu Lab A1 mini 0.4 nozzle"]


def test_missing_parent_is_reported(resources, data_dir):
    store = ProfileStore.load(resources, data_dir)
    with pytest.raises(ProfileNotFoundError) as exc:
        store.resolve("Orphan")
    assert exc.value.details["missing_parent"] == "Deleted Parent"


def test_inheritance_cycle_detected(resources):
    bbl = resources / "profiles" / "BBL" / "process"
    write_json(bbl / "a.json", {"type": "process", "name": "A", "inherits": "B", "instantiation": "true"})
    write_json(bbl / "b.json", {"type": "process", "name": "B", "inherits": "A", "instantiation": "false"})
    store = ProfileStore.load(resources, None)
    with pytest.raises(InheritanceCycleError) as exc:
        store.resolve("A")
    assert exc.value.details["cycle"] == ["A", "B", "A"]


def test_invalid_json_is_collected_not_fatal(resources):
    bad = resources / "profiles" / "BBL" / "process" / "broken.json"
    bad.write_text("{ not json", encoding="utf-8")
    store = ProfileStore.load(resources, None)
    assert any("broken.json" in e for e in store.load_errors)
    assert store.resolve("0.20mm Standard @BBL A1M")


def test_type_mismatch(resources):
    store = ProfileStore.load(resources, None)
    with pytest.raises(ProfileError):
        store.find("0.20mm Standard @BBL A1M", ptype="machine")


def test_compatibility(resources):
    store = ProfileStore.load(resources, None)
    a1m = store.resolve("Bambu Lab A1 mini 0.4 nozzle")
    ok, _ = store.compatibility(store.resolve("0.20mm Standard @BBL A1M"), a1m)
    bad, reason = store.compatibility(store.resolve("0.20mm Standard @BBL X1C"), a1m)
    assert ok is True and bad is False and "compatible_printers" in reason


def test_listing_hides_abstract_profiles(resources):
    store = ProfileStore.load(resources, None)
    names = {r.name for r in store.list(ptype="process")}
    assert "fdm_process_common" not in names
    assert "fdm_process_common" in {r.name for r in store.list(ptype="process", include_abstract=True)}


def test_export_unchanged_system_profile(resources):
    store = ProfileStore.load(resources, None)
    out = export_for_cli(store.resolve("Bambu PLA Basic @BBL A1M"))
    assert out["from"] == "system" and out["name"] == "Bambu PLA Basic @BBL A1M"
    assert out["filament_id"] == "GFA00" and out["type"] == "filament"


def test_export_with_overrides_becomes_user_copy(resources):
    store = ProfileStore.load(resources, None)
    base = store.resolve("0.20mm Standard @BBL A1M")
    out = export_for_cli(base, name="copy", overrides={"wall_loops": "4"})
    assert out["from"] == "User" and out["inherits"] == "0.20mm Standard @BBL A1M"
    assert out["wall_loops"] == "4"
    assert base.get("wall_loops") == "2"  # original untouched
    assert diff_values(base.values, out) == [{"key": "wall_loops", "before": "2", "after": "4"}]


def test_original_files_are_not_modified(resources):
    path = resources / "profiles" / "BBL" / "process" / "0.20mm Standard @BBL A1M.json"
    before = path.read_bytes()
    store = ProfileStore.load(resources, None)
    export_for_cli(store.resolve("0.20mm Standard @BBL A1M"), name="x", overrides={"wall_loops": "9"})
    assert path.read_bytes() == before
