"""Operating-system specific default locations for Bambu Studio.

Defaults are only candidates. Every path can be overridden via CLI option,
environment variable or ``bambu-butler.json`` (see ``settings.py``).
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


def current_os() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


@dataclass(frozen=True)
class Candidates:
    executables: list[Path]
    resources: list[Path]
    data_dirs: list[Path]


def _home() -> Path:
    return Path.home()


def candidates(os_name: str | None = None) -> Candidates:
    os_name = os_name or current_os()
    if os_name == "macos":
        apps = [Path("/Applications/BambuStudio.app"), _home() / "Applications/BambuStudio.app"]
        return Candidates(
            executables=[a / "Contents/MacOS/BambuStudio" for a in apps],
            resources=[a / "Contents/Resources" for a in apps],
            data_dirs=[_home() / "Library/Application Support/BambuStudio"],
        )
    if os_name == "windows":
        program_files = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        ]
        roots = [p / "Bambu Studio" for p in program_files]
        appdata = Path(os.environ.get("APPDATA", str(_home() / "AppData/Roaming")))
        return Candidates(
            executables=[r / "bambu-studio.exe" for r in roots],
            resources=[r / "resources" for r in roots],
            data_dirs=[appdata / "BambuStudio"],
        )
    # Linux: AppImage users usually have no fixed install location; PATH lookup
    # is added in ``find_executable``. Flatpak keeps its data in ~/.var.
    return Candidates(
        executables=[
            Path("/opt/bambu-studio/bin/bambu-studio"),
            Path("/usr/bin/bambu-studio"),
            Path("/usr/local/bin/bambu-studio"),
            _home() / "Applications/BambuStudio.AppImage",
        ],
        resources=[
            Path("/opt/bambu-studio/resources"),
            Path("/usr/share/bambu-studio"),
            Path("/usr/share/BambuStudio"),
        ],
        data_dirs=[
            _home() / ".config/BambuStudio",
            _home() / ".var/app/com.bambulab.BambuStudio/config/BambuStudio",
        ],
    )


PATH_NAMES = ("bambu-studio", "BambuStudio", "bambu-studio.exe")


def find_executable(os_name: str | None = None) -> Path | None:
    for path in candidates(os_name).executables:
        if path.is_file():
            return path
    for name in PATH_NAMES:
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def resources_for_executable(executable: Path) -> list[Path]:
    """Derive likely resource directories from an executable location."""
    exe = executable.resolve() if executable.exists() else executable
    out: list[Path] = []
    for parent in list(exe.parents)[:4]:
        out.append(parent / "Resources")  # macOS app bundle
        out.append(parent / "resources")  # Windows / Linux builds
    return out


def find_resources(executable: Path | None, os_name: str | None = None) -> Path | None:
    options = (resources_for_executable(executable) if executable else []) + candidates(os_name).resources
    for path in options:
        if (path / "profiles").is_dir():
            return path
    return None


def find_data_dir(os_name: str | None = None) -> Path | None:
    for path in candidates(os_name).data_dirs:
        if path.is_dir():
            return path
    return None
