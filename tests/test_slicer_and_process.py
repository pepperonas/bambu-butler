import sys
import zipfile
from pathlib import Path

import pytest

from bambu_butler import process, slicer, studio
from bambu_butler.errors import UnsafeArgumentError
from bambu_butler.plan import Transform


def cmd(tmp_path, **kw):
    d = tmp_path / "job dir with spaces"
    args = dict(model=d / "input/my model.stl", machine=d / "profiles/machine.json",
                process=d / "profiles/process.json", filaments=[d / "profiles/filament_1.json"],
                outputdir=d, export_name="job.3mf", slice_plates=True, transform=Transform())
    args.update(kw)
    return slicer.build_command(Path("/Applications/Bambu Studio.app/Contents/MacOS/BambuStudio"), **args)


def test_command_is_argument_list_with_spaces(tmp_path):
    argv = cmd(tmp_path)
    assert argv[0].endswith("BambuStudio") and " " in argv[0]
    assert argv[-1].endswith("input/my model.stl")
    i = argv.index("--load-settings")
    assert argv[i + 1].count(";") == 1 and "job dir with spaces" in argv[i + 1]
    assert argv[argv.index("--slice") + 1] == "0"
    assert argv[argv.index("--export-3mf") + 1] == "job.3mf"
    assert all(isinstance(a, str) for a in argv)


def test_prepare_mode_has_no_slice(tmp_path):
    assert "--slice" not in cmd(tmp_path, slice_plates=False)


def test_transform_flags(tmp_path):
    argv = cmd(tmp_path, transform=Transform(rotate_x_deg=90, rotate_z_deg=45, scale=1.5, auto_orient=True))
    assert argv[argv.index("--rotate-x") + 1] == "90"
    assert argv[argv.index("--rotate") + 1] == "45"
    assert argv[argv.index("--scale") + 1] == "1.5"
    assert "--ensure-on-bed" in argv
    assert argv[argv.index("--orient") + 1] == "1"


@pytest.mark.parametrize("bad", ["a;b", 'a"b'])
def test_semicolons_and_quotes_rejected_in_list_paths(tmp_path, bad):
    with pytest.raises(UnsafeArgumentError):
        cmd(tmp_path, machine=tmp_path / bad / "machine.json")


def test_export_name_and_dash_model_rejected(tmp_path):
    with pytest.raises(UnsafeArgumentError):
        cmd(tmp_path, export_name="../x.3mf")
    with pytest.raises(UnsafeArgumentError):
        cmd(tmp_path, model=Path("-evil.stl"))


def test_shell_metacharacters_are_not_interpreted(tmp_path):
    marker = tmp_path / "pwned"
    result = process.run([sys.executable, "-c", "import sys; print(sys.argv[1])", f"; touch {marker}"],
                         timeout=10)
    assert result.returncode == 0 and "touch" in result.stdout
    assert not marker.exists()


def test_argv_validation():
    with pytest.raises(UnsafeArgumentError):
        process.ensure_argv("echo hi")  # type: ignore[arg-type]
    with pytest.raises(UnsafeArgumentError):
        process.ensure_argv(["a\x00b"])


def test_timeout_kills_process():
    result = process.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
    assert result.timed_out and result.returncode is None and result.duration_seconds < 15


def test_describe_exit_handles_posix_wraparound():
    assert slicer.describe_exit(0)["name"] == "CLI_SUCCESS"
    assert slicer.describe_exit(256 - 100)["name"] == "CLI_SLICING_ERROR"
    assert slicer.describe_exit(-17)["name"] == "CLI_PROCESS_NOT_COMPATIBLE"
    assert slicer.describe_exit(None)["code"] is None


def test_slice_info_parsing(tmp_path):
    p = tmp_path / "s.3mf"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("Metadata/plate_1.gcode", "")
        z.writestr("Metadata/slice_info.config",
                   '<config><plate><metadata key="index" value="1"/><metadata key="prediction" value="3723"/>'
                   '<metadata key="weight" value="12.34"/><filament id="1" type="PLA" used_g="12.34"/>'
                   '<warning msg="w1"/></plate></config>')
    info = slicer.read_slice_info(p)
    summary = slicer.summarize_slice(None, info)
    assert summary["print_time_seconds"] == 3723 and summary["filament_g"] == 12.34
    assert info["plates"][0]["warnings"] == ["w1"]
    assert slicer.format_duration(3723) == "1 h 02 min"


def test_no_summary_without_real_output(tmp_path):
    p = tmp_path / "unsliced.3mf"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("3D/3dmodel.model", "<model/>")
    assert slicer.read_slice_info(p) is None
    assert slicer.summarize_slice(None, None) is None


def test_help_parsing():
    text = "BambuStudio-02.08.04.57:\n  --slice option\n  --export-3mf filename.3mf\n --load-settings x\n"
    version, options = studio.parse_help(text)
    assert version == "02.08.04.57"
    assert {"--slice", "--export-3mf", "--load-settings"} <= set(options)


def test_detect_missing_executable(tmp_path):
    info = studio.detect(tmp_path / "missing")
    assert not info.exists and not info.cli_usable and info.problems
    assert not studio.detect(None).cli_usable


def test_detect_fake_studio(fake_studio):
    info = studio.detect(fake_studio)
    assert info.cli_usable and info.version == "02.08.04.57"
