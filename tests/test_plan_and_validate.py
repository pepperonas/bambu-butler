import json
from pathlib import Path

import pytest

from bambu_butler.errors import PlanError
from bambu_butler.plan import json_schema, parse_plan
from bambu_butler.profiles import ProfileStore
from bambu_butler.validate import validate_plan

from .conftest import box_triangles, make_3mf, write_binary_stl

ROOT = Path(__file__).resolve().parents[1]


def run(plan_dict, workdir, resources, data_dir=None):
    plan_path = workdir / "plan.json"
    plan_path.write_text(json.dumps(plan_dict), encoding="utf-8")
    return validate_plan(parse_plan(plan_dict), plan_path, ProfileStore.load(resources, data_dir))


def codes(result):
    return {i.code for i in result.errors}


def test_schema_rejects_unknown_fields(plan_dict):
    plan_dict["settings"]["strength"]["walls"] = 3
    with pytest.raises(PlanError) as exc:
        parse_plan(plan_dict)
    assert "settings.strength.walls" in exc.value.message


def test_schema_rejects_wrong_model_type(plan_dict):
    plan_dict["model"]["path"] = "part.step"
    with pytest.raises(PlanError):
        parse_plan(plan_dict)


def test_schema_rejects_locked_machine_keys(plan_dict):
    plan_dict["overrides"] = {"machine": {"printable_height": "300"}}
    with pytest.raises(PlanError):
        parse_plan(plan_dict)


def test_committed_schema_is_current():
    committed = json.loads((ROOT / "schemas" / "print-plan.v1.schema.json").read_text())
    assert committed == json.loads(json.dumps(json_schema()))


def test_examples_are_schema_valid():
    for path in (ROOT / "examples").glob("*.plan.json"):
        parse_plan(json.loads(path.read_text()))


def test_valid_plan_is_compatible(plan_dict, workdir, resources):
    r = run(plan_dict, workdir, resources)
    assert r.compatible, r.issues
    assert r.process_overrides["wall_loops"] == "4"
    assert r.process_overrides["sparse_infill_density"] == "25%"
    assert r.process_overrides["support_type"] == "tree(auto)"
    assert r.process_overrides["enable_support"] == "1"
    assert r.model_report["fit"]["fits"]


def test_incompatible_filament(plan_dict, workdir, resources):
    plan_dict["filaments"] = [{"profile": "Bambu PETG Basic @BBL X1C"}]
    assert "incompatible_profile" in codes(run(plan_dict, workdir, resources))


def test_incompatible_process(plan_dict, workdir, resources):
    plan_dict["process"]["profile"] = "0.20mm Standard @BBL X1C"
    assert "incompatible_profile" in codes(run(plan_dict, workdir, resources))


def test_material_mismatch(plan_dict, workdir, resources):
    plan_dict["filaments"][0]["material"] = "PETG"
    assert "material_mismatch" in codes(run(plan_dict, workdir, resources))


def test_nozzle_mismatch(plan_dict, workdir, resources):
    plan_dict["printer"]["nozzle_diameter_mm"] = 0.6
    assert "nozzle_mismatch" in codes(run(plan_dict, workdir, resources))


def test_unknown_profile(plan_dict, workdir, resources):
    plan_dict["printer"]["profile"] = "Bambu Lab Z9"
    assert "profile_not_found" in codes(run(plan_dict, workdir, resources))


def test_abstract_profile_rejected(plan_dict, workdir, resources):
    plan_dict["process"]["profile"] = "fdm_process_common"
    assert "profile_not_instantiable" in codes(run(plan_dict, workdir, resources))


def test_unknown_raw_override(plan_dict, workdir, resources):
    plan_dict["overrides"] = {"process": {"made_up_key": "1"}}
    assert "unknown_key" in codes(run(plan_dict, workdir, resources))


def test_raw_override_keeps_vector_shape(plan_dict, workdir, resources):
    plan_dict["overrides"] = {"process": {"outer_wall_speed": 150}}
    r = run(plan_dict, workdir, resources)
    assert r.process_overrides["outer_wall_speed"] == ["150"]


def test_override_conflict(plan_dict, workdir, resources):
    plan_dict["overrides"] = {"process": {"wall_loops": "3"}}
    assert "override_conflict" in codes(run(plan_dict, workdir, resources))


def test_layer_height_limits(plan_dict, workdir, resources):
    plan_dict["settings"]["quality"]["layer_height_mm"] = 0.4
    assert "layer_height_out_of_range" in codes(run(plan_dict, workdir, resources))


def test_model_too_large(plan_dict, workdir, resources):
    write_binary_stl(workdir / "big.stl", box_triangles(200, 50, 50))
    plan_dict["model"]["path"] = "big.stl"
    assert "model_too_large" in codes(run(plan_dict, workdir, resources))


def test_transform_is_used_for_fit(plan_dict, workdir, resources):
    write_binary_stl(workdir / "tall.stl", box_triangles(20, 30, 170))
    plan_dict["model"]["path"] = "tall.stl"
    plan_dict["transform"] = {"rotate_x_deg": 90}
    r = run(plan_dict, workdir, resources)
    assert r.compatible
    assert r.model_report["size_after_transform_mm"] == [20, 170, 30]
    plan_dict["transform"] = {"scale": 1.1}
    assert "model_too_large" in codes(run(plan_dict, workdir, resources))


def test_missing_model(plan_dict, workdir, resources):
    plan_dict["model"]["path"] = "nope.stl"
    assert "model_file_error" in codes(run(plan_dict, workdir, resources))


def test_3mf_filament_slots_must_exist(plan_dict, workdir, resources):
    make_3mf(workdir / "multi.3mf")
    plan_dict["model"]["path"] = "multi.3mf"
    r = run(plan_dict, workdir, resources)
    assert "filament_slot_missing" in codes(r)
    assert any(i.code == "filament_count_changes" for i in r.warnings)
    plan_dict["filaments"] *= 2
    assert run(plan_dict, workdir, resources).compatible


def test_blocking_question_reported(plan_dict, workdir, resources):
    plan_dict["open_questions"] = [{"question": "Welche Belastungsrichtung?", "blocking": True}]
    r = run(plan_dict, workdir, resources)
    assert r.compatible and r.blocking_questions == ["Welche Belastungsrichtung?"]
