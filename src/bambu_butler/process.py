"""Safe execution of external programs: argument lists only, never shell strings."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .errors import UnsafeArgumentError


@dataclass
class RunResult:
    argv: list[str]
    returncode: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool

    def to_dict(self) -> dict:
        return {
            "argv": self.argv,
            "returncode": self.returncode,
            "duration_seconds": round(self.duration_seconds, 3),
            "timed_out": self.timed_out,
        }


def ensure_argv(argv: list) -> list[str]:
    """Validate an argument vector before it reaches ``subprocess``."""
    if not isinstance(argv, list) or not argv:
        raise UnsafeArgumentError("Befehl muss eine nicht-leere Argumentliste sein.")
    out: list[str] = []
    for arg in argv:
        if isinstance(arg, Path):
            arg = str(arg)
        if not isinstance(arg, str):
            raise UnsafeArgumentError(f"Ungültiges Argument (kein String): {arg!r}")
        if "\x00" in arg:
            raise UnsafeArgumentError("Argument enthält ein NUL-Zeichen.")
        out.append(arg)
    return out


def run(argv: list, *, timeout: float, cwd: Path | None = None, env: dict | None = None) -> RunResult:
    """Run ``argv`` without a shell and kill the whole process group on timeout."""
    argv = ensure_argv(argv)
    kwargs: dict = {}
    if os.name == "posix":
        kwargs["start_new_session"] = True
    else:  # pragma: no cover - Windows only
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    started = time.monotonic()
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        **kwargs,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        _terminate(proc)
        stdout, stderr = proc.communicate()
        timed_out = True
    return RunResult(argv, None if timed_out else proc.returncode, stdout or "", stderr or "",
                     time.monotonic() - started, timed_out)


def _terminate(proc: subprocess.Popen) -> None:
    if os.name == "posix":
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(proc.pid, sig)
            except ProcessLookupError:
                return
            try:
                proc.wait(timeout=5)
                return
            except subprocess.TimeoutExpired:
                continue
    else:  # pragma: no cover - Windows only
        proc.kill()


def spawn_detached(argv: list) -> None:
    """Start a GUI program without waiting for it."""
    argv = ensure_argv(argv)
    kwargs: dict = {"start_new_session": True} if os.name == "posix" else {}
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, shell=False, **kwargs)
