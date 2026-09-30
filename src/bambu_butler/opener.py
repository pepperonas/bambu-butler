"""Open a project in Bambu Studio using operating-system facilities."""

from __future__ import annotations

import os
from pathlib import Path

from . import process
from .errors import ButlerError, ModelFileError
from .platforms import current_os


def _app_bundle(executable: Path | None) -> Path | None:
    if not executable:
        return None
    for parent in executable.parents:
        if parent.suffix == ".app":
            return parent
    return None


def open_command(project: Path, executable: Path | None, os_name: str | None = None) -> list[str] | None:
    """Return the argv used to open ``project``; ``None`` means ``os.startfile`` (Windows default)."""
    os_name = os_name or current_os()
    project_arg = str(project)
    if os_name == "macos":
        bundle = _app_bundle(executable)
        if bundle:
            return ["open", "-a", str(bundle), project_arg]
        return ["open", "-a", "BambuStudio", project_arg]
    if os_name == "windows":
        return [str(executable), project_arg] if executable else None
    if executable:
        return [str(executable), project_arg]
    return ["xdg-open", project_arg]


def open_project(project: Path, executable: Path | None, *, dry_run: bool = False) -> dict:
    project = Path(project).resolve()
    if not project.is_file():
        raise ModelFileError(f"Projektdatei nicht gefunden: {project}")
    if project.suffix.lower() not in (".3mf", ".stl"):
        raise ModelFileError("Nur .3mf- und .stl-Dateien können geöffnet werden.")
    argv = open_command(project, executable)
    info = {"project": str(project), "argv": argv, "opened": False}
    if dry_run:
        return info
    try:
        if argv is None:  # pragma: no cover - Windows only
            os.startfile(str(project))  # type: ignore[attr-defined]
        else:
            process.spawn_detached(argv)
    except OSError as exc:
        raise ButlerError(f"Bambu Studio konnte nicht geöffnet werden: {exc}",
                          hint=f"Datei manuell in Bambu Studio öffnen: {project}") from exc
    info["opened"] = True
    return info
