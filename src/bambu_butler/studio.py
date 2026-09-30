"""Bambu Studio installation detection: executable, version and CLI capabilities."""

from __future__ import annotations

import plistlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import process

# CLI options Bambu Butler relies on. Verified against src/libslic3r/PrintConfig.cpp
# (CLIActionsConfigDef / CLITransformConfigDef / CLIMiscConfigDef) of BambuStudio v02.08.
REQUIRED_OPTIONS = ("--load-settings", "--load-filaments", "--export-3mf", "--outputdir", "--slice")
OPTIONAL_OPTIONS = (
    "--orient", "--arrange", "--scale", "--rotate", "--rotate-x", "--rotate-y",
    "--ensure-on-bed", "--debug", "--export-settings", "--info", "--allow-newer-file",
)

_VERSION_RE = re.compile(r"BambuStudio-(\d+(?:\.\d+){1,3})")
_OPTION_RE = re.compile(r"^\s*(--[a-z0-9][a-z0-9-]*)", re.MULTILINE)


@dataclass
class StudioInfo:
    executable: Path | None
    exists: bool = False
    version: str | None = None
    version_source: str | None = None
    help_available: bool = False
    options: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def missing_required(self) -> list[str]:
        if not self.help_available:
            return []
        return [o for o in REQUIRED_OPTIONS if o not in self.options]

    @property
    def cli_usable(self) -> bool:
        return self.exists and self.help_available and not self.missing_required

    def to_dict(self) -> dict:
        return {
            "executable": str(self.executable) if self.executable else None,
            "exists": self.exists,
            "version": self.version,
            "version_source": self.version_source,
            "help_available": self.help_available,
            "cli_usable": self.cli_usable,
            "required_options": {o: (o in self.options) if self.help_available else None
                                 for o in REQUIRED_OPTIONS},
            "optional_options": {o: (o in self.options) if self.help_available else None
                                 for o in OPTIONAL_OPTIONS},
            "problems": self.problems,
        }


def parse_help(text: str) -> tuple[str | None, list[str]]:
    version_match = _VERSION_RE.search(text)
    options = sorted(set(_OPTION_RE.findall(text)))
    return (version_match.group(1) if version_match else None), options


def _app_bundle(executable: Path) -> Path | None:
    for parent in executable.parents:
        if parent.suffix == ".app":
            return parent
    return None


def version_from_bundle(executable: Path) -> str | None:
    bundle = _app_bundle(executable)
    if not bundle:
        return None
    plist = bundle / "Contents/Info.plist"
    try:
        with plist.open("rb") as fh:
            data = plistlib.load(fh)
    except (OSError, plistlib.InvalidFileException):
        return None
    return data.get("CFBundleShortVersionString") or data.get("CFBundleVersion")


def detect(executable: Path | None, *, timeout: float = 60) -> StudioInfo:
    info = StudioInfo(executable=executable)
    if executable is None:
        info.problems.append("Bambu Studio wurde nicht gefunden.")
        return info
    if not executable.is_file():
        info.problems.append(f"Bambu-Studio-Executable existiert nicht: {executable}")
        return info
    info.exists = True

    bundle_version = version_from_bundle(executable)
    if bundle_version:
        info.version, info.version_source = bundle_version, "Info.plist"

    try:
        result = process.run([str(executable), "--help"], timeout=timeout)
    except OSError as exc:
        info.problems.append(f"Bambu Studio konnte nicht gestartet werden: {exc}")
        return info
    if result.timed_out:
        info.problems.append(f"'--help' hat nach {timeout:.0f}s nicht geantwortet.")
        return info
    version, options = parse_help(result.stdout + "\n" + result.stderr)
    if options:
        info.help_available = True
        info.options = options
    else:
        info.problems.append("Die CLI-Hilfe von Bambu Studio enthielt keine erkennbaren Optionen.")
    if version and not info.version:
        info.version, info.version_source = version, "--help"
    if info.missing_required:
        info.problems.append("Benötigte CLI-Optionen fehlen: " + ", ".join(info.missing_required))
    return info
