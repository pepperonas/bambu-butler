"""Optional macOS GUI adapter for Bambu Studio (AppleScript / Accessibility).

Scope, deliberately small:

* Bambu Studio has no documented AppleScript dictionary. Only generic
  ``System Events`` functionality (activate the app, read window titles) is
  used; that works for any app once Automation/Accessibility is granted.
* No screen coordinates, no synthetic clicks or key presses into unknown
  dialogs. Anything beyond "activate" and "check the front window" ends in a
  clear manual instruction.

The core workflow (prepare + slice via CLI) never depends on this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import process
from .platforms import current_os

APP_NAME = "BambuStudio"


@dataclass
class GuiCheck:
    supported_os: bool
    osascript: bool = False
    automation_permission: bool | None = None
    accessibility_permission: bool | None = None
    app_running: bool | None = None
    window_titles: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _osascript(script: str, timeout: float = 10) -> tuple[bool, str]:
    result = process.run(["osascript", "-e", script], timeout=timeout)
    if result.timed_out:
        return False, "Zeitüberschreitung bei osascript"
    return result.returncode == 0, (result.stdout or result.stderr).strip()


def check(expected_file: str | None = None) -> GuiCheck:
    info = GuiCheck(supported_os=current_os() == "macos")
    if not info.supported_os:
        info.problems.append("GUI-Automation ist nur für macOS implementiert.")
        return info
    import shutil

    info.osascript = shutil.which("osascript") is not None
    if not info.osascript:
        info.problems.append("osascript wurde nicht gefunden.")
        return info
    ok, out = _osascript('tell application "System Events" to get UI elements enabled')
    if not ok:
        info.automation_permission = False
        info.problems.append(
            "Keine Automations-Berechtigung für System Events. Freigeben unter Systemeinstellungen > "
            "Datenschutz & Sicherheit > Automation (Terminal bzw. Claude Code -> System Events). "
            f"Meldung: {out}")
        return info
    info.automation_permission = True
    info.accessibility_permission = out.lower() == "true"
    if not info.accessibility_permission:
        info.problems.append(
            "Bedienungshilfen-Zugriff fehlt. Freigeben unter Systemeinstellungen > Datenschutz & Sicherheit > "
            "Bedienungshilfen für das Terminal-Programm.")
    ok, out = _osascript(f'tell application "System Events" to (name of processes) contains "{APP_NAME}"')
    info.app_running = ok and out.lower() == "true"
    if info.app_running and info.accessibility_permission:
        ok, out = _osascript(
            f'tell application "System Events" to tell process "{APP_NAME}" to get name of every window')
        if ok and out:
            info.window_titles = [t.strip() for t in out.split(",") if t.strip()]
    if expected_file and info.window_titles and not any(expected_file in t for t in info.window_titles):
        info.problems.append(
            f"Kein Bambu-Studio-Fenster zeigt '{expected_file}'. Möglicherweise ist ein Dialog offen "
            "(z. B. Speichern/Update). Es wird nichts automatisch bestätigt.")
    return info


def activate() -> tuple[bool, str]:
    if current_os() != "macos":
        return False, "Nur unter macOS verfügbar."
    return _osascript(f'tell application "{APP_NAME}" to activate')


MANUAL_STEPS = {
    "slice": "In Bambu Studio oben rechts auf 'Platte slicen' klicken und die Vorschau prüfen.",
    "send": "Druck nur manuell über 'Drucken' in Bambu Studio senden, nachdem die Vorschau geprüft wurde.",
    "dialog": "Offene Dialoge in Bambu Studio manuell prüfen und bestätigen.",
}
