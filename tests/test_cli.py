import json

import pytest
from typer.testing import CliRunner

from bambu_butler.cli import app
from bambu_butler.settings import load_settings

runner = CliRunner()


def invoke(*args, env=None):
    result = runner.invoke(app, [str(a) for a in args], env=env)
    return result


def as_json(result):
    return json.loads(result.stdout)


@pytest.fixture
def plan_file(workdir, plan_dict):
    p = workdir / "halter plan.json"
    p.write_text(json.dumps(plan_dict), encoding="utf-8")
    return p


def base_args(resources, tmp_path, studio=None):
    args = ["--json", "--resources", resources, "--jobs-dir", tmp_path / "jobs out"]
    args += ["--studio", studio or (tmp_path / "no-studio")]
    return args


def test_doctor_without_studio(resources, tmp_path):
    r = invoke(*base_args(resources, tmp_path), "doctor")
    data = as_json(r)
    assert r.exit_code == 0 and data["ok"]
    assert data["can_slice"] is False
    assert "Bambu Studio (Executable)" in data["missing"]
    assert data["profile_counts"]["machine"]["system"] == 2
    r = invoke(*base_args(resources, tmp_path), "doctor", "--strict")
    assert r.exit_code == 3


def test_doctor_does_not_print_secrets(resources, data_dir, tmp_path):
    (data_dir / "BambuStudio.conf").write_text('{"access_token": "SECRET-TOKEN-123"}')
    r = invoke(*base_args(resources, tmp_path), "--data-dir", data_dir, "doctor")
    assert "SECRET-TOKEN-123" not in r.stdout


def test_doctor_with_fake_studio(resources, tmp_path, fake_studio):
    data = as_json(invoke(*base_args(resources, tmp_path, fake_studio), "doctor"))
    assert data["can_slice"] is True and data["studio"]["version"] == "02.08.04.57"


def test_profiles_list_and_show(resources, data_dir, tmp_path):
    args = base_args(resources, tmp_path) + ["--data-dir", data_dir]
    data = as_json(invoke(*args, "profiles", "list", "--type", "process",
                          "--printer", "Bambu Lab A1 mini 0.4 nozzle"))
    names = [p["name"] for p in data["profiles"]]
    assert "0.20mm Standard @BBL A1M" in names and "My Strong" in names
    assert "0.20mm Standard @BBL X1C" not in names
    data = as_json(invoke(*args, "profiles", "show", "My Strong", "--keys", "wall_loops,layer_height"))
    assert data["values"] == {"wall_loops": "5", "layer_height": "0.2"}
    r = invoke(*args, "profiles", "show", "Orphan")
    assert r.exit_code == 1 and as_json(r)["error"]["code"] == "profile_not_found"


def test_inspect(resources, workdir, tmp_path):
    data = as_json(invoke(*base_args(resources, tmp_path), "inspect", workdir / "halter mit leerzeichen.stl",
                          "--printer", "Bambu Lab A1 mini 0.4 nozzle"))
    assert data["model"]["fit"]["fits"] is True
    assert "nicht sicher bestimmen" in data["model"]["limits"]


def test_validate_ok_and_incompatible(resources, plan_file, plan_dict, tmp_path):
    data = as_json(invoke(*base_args(resources, tmp_path), "validate", plan_file))
    assert data["validation"]["stages"] == {"schema_valid": True, "compatible_with_profiles": True,
                                            "sliced": False}
    plan_dict["filaments"] = [{"profile": "Bambu PETG Basic @BBL X1C"}]
    plan_file.write_text(json.dumps(plan_dict))
    r = invoke(*base_args(resources, tmp_path), "validate", plan_file)
    assert r.exit_code == 2 and not as_json(r)["validation"]["stages"]["compatible_with_profiles"]


def test_validate_schema_error(resources, plan_file, tmp_path):
    plan_file.write_text('{"schema_version": "1"}')
    r = invoke(*base_args(resources, tmp_path), "validate", plan_file)
    assert r.exit_code == 2 and as_json(r)["error"]["code"] == "plan_invalid"


def test_dry_run_writes_nothing(resources, plan_file, tmp_path, fake_studio):
    data = as_json(invoke(*base_args(resources, tmp_path, fake_studio), "slice", plan_file, "--dry-run"))
    assert data["job"]["status"] == "dry_run"
    assert "--slice" in data["job"]["command"]
    assert not (tmp_path / "jobs out").exists()
    assert not (tmp_path / "fake-argv.json").exists()


def test_prepare_without_studio(resources, plan_file, tmp_path):
    r = invoke(*base_args(resources, tmp_path), "prepare", plan_file)
    data = as_json(r)
    assert r.exit_code == 0 and data["job"]["status"] == "prepared_without_studio"
    assert data["job"]["stages"]["sliced"] is False
    job_dir = tmp_path / "jobs out"
    (d,) = list(job_dir.iterdir())
    for f in ("plan.json", "profiles/process.json", "changes.json", "command.json", "report.md",
              "input/halter mit leerzeichen.stl"):
        assert (d / f).is_file(), f
    process = json.loads((d / "profiles/process.json").read_text())
    assert process["from"] == "User" and process["wall_loops"] == "4"


def test_slice_without_studio_fails_clearly(resources, plan_file, tmp_path):
    r = invoke(*base_args(resources, tmp_path), "slice", plan_file)
    assert r.exit_code == 3
    assert as_json(r)["error"]["code"] == "studio_not_found"


def test_slice_with_fake_studio(resources, plan_file, tmp_path, fake_studio):
    r = invoke(*base_args(resources, tmp_path, fake_studio), "slice", plan_file)
    data = as_json(r)
    assert r.exit_code == 0, r.stdout
    job = data["job"]
    assert job["status"] == "sliced" and job["print_started"] is False
    assert job["result"]["print_time_seconds"] == 3723 and job["result"]["filament_g"] == 12.34
    argv = json.loads((tmp_path / "fake-argv.json").read_text())
    assert argv[-1].endswith("input/halter mit leerzeichen.stl")
    report = (tmp_path / "jobs out").glob("*/report.md")
    assert "Erfolgreich von Bambu Studio geslict" in next(report).read_text()


def test_slice_failure_is_reported(resources, plan_file, tmp_path, fake_studio, monkeypatch):
    monkeypatch.setenv("FAKE_STUDIO_MODE", "fail")
    r = invoke(*base_args(resources, tmp_path, fake_studio), "slice", plan_file)
    err = as_json(r)["error"]
    assert r.exit_code == 4 and err["code"] == "slicer_failed"
    assert err["details"]["exit"]["name"] == "CLI_SLICING_ERROR"


def test_success_without_gcode_is_not_sliced(resources, plan_file, tmp_path, fake_studio, monkeypatch):
    monkeypatch.setenv("FAKE_STUDIO_MODE", "nogcode")
    r = invoke(*base_args(resources, tmp_path, fake_studio), "slice", plan_file)
    assert r.exit_code == 4


def test_slice_timeout(resources, plan_file, tmp_path, fake_studio, monkeypatch):
    monkeypatch.setenv("FAKE_STUDIO_MODE", "hang")
    r = invoke(*base_args(resources, tmp_path, fake_studio), "slice", plan_file, "--timeout", "2")
    assert as_json(r)["error"]["code"] == "slicer_timeout"


def test_prepare_with_fake_studio_exports_unsliced(resources, plan_file, tmp_path, fake_studio):
    data = as_json(invoke(*base_args(resources, tmp_path, fake_studio), "prepare", plan_file))
    assert data["job"]["status"] == "prepared"
    assert "--slice" not in data["job"]["command"]
    assert data["job"]["result"] is None


def test_blocking_questions_stop_slicing(resources, plan_file, plan_dict, tmp_path, fake_studio):
    plan_dict["open_questions"] = [{"question": "Welches Material?", "blocking": True}]
    plan_file.write_text(json.dumps(plan_dict))
    r = invoke(*base_args(resources, tmp_path, fake_studio), "slice", plan_file)
    assert r.exit_code == 1 and "Welches Material" in as_json(r)["error"]["message"]


def test_open_dry_run(resources, tmp_path, workdir):
    target = workdir / "halter mit leerzeichen.stl"
    data = as_json(invoke(*base_args(resources, tmp_path), "open", target, "--dry-run"))
    assert data["argv"][-1] == str(target.resolve()) and data["opened"] is False


def test_printer_control_not_implemented(resources, tmp_path):
    r = invoke("--json", "printer", "start", "x.3mf")
    assert r.exit_code == 5 and as_json(r)["error"]["code"] == "not_supported"


def test_init_and_template(resources, tmp_path, workdir):
    r = invoke("--json", "--resources", resources, "init", tmp_path / "project dir")
    assert r.exit_code == 0
    cfg = json.loads((tmp_path / "project dir" / "bambu-butler.json").read_text())
    assert cfg["resources_dir"] == str(resources) and cfg["jobs_dir"] == "jobs"
    out = workdir / "plans" / "t.plan.json"
    r = invoke("--json", "--resources", resources, "template", workdir / "halter mit leerzeichen.stl",
               "--printer", "Bambu Lab A1 mini 0.4 nozzle", "-o", out)
    plan = json.loads(out.read_text())
    assert plan["process"]["profile"] == "0.20mm Standard @BBL A1M"
    assert plan["model"]["path"] == "../halter mit leerzeichen.stl"


def test_settings_precedence(tmp_path, monkeypatch):
    cfg = tmp_path / "bambu-butler.json"
    cfg.write_text(json.dumps({"studio_executable": "from-config", "timeout_seconds": 5, "jobs_dir": "j"}))
    s = load_settings(config_path=cfg, autodetect=False)
    assert s.studio_executable.name == "from-config" and s.timeout_seconds == 5
    assert s.jobs_dir == tmp_path / "j"
    monkeypatch.setenv("BAMBU_BUTLER_STUDIO", "/env/studio")
    assert str(load_settings(config_path=cfg, autodetect=False).studio_executable) == "/env/studio"
    s = load_settings({"studio_executable": "/cli/studio"}, config_path=cfg, autodetect=False)
    assert str(s.studio_executable) == "/cli/studio" and s.sources["studio_executable"] == "cli"
