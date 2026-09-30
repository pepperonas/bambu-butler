"""Runtime settings: CLI option > environment variable > bambu-butler.json > auto-detection."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import platforms
from .errors import ConfigError

CONFIG_FILENAME = "bambu-butler.json"
DEFAULT_TIMEOUT = 600

ENV = {
    "studio_executable": "BAMBU_BUTLER_STUDIO",
    "resources_dir": "BAMBU_BUTLER_RESOURCES",
    "data_dir": "BAMBU_BUTLER_DATA_DIR",
    "jobs_dir": "BAMBU_BUTLER_JOBS_DIR",
    "timeout_seconds": "BAMBU_BUTLER_TIMEOUT",
}


@dataclass
class Settings:
    studio_executable: Path | None = None
    resources_dir: Path | None = None
    data_dir: Path | None = None
    jobs_dir: Path = Path("jobs")
    timeout_seconds: int = DEFAULT_TIMEOUT
    config_file: Path | None = None
    sources: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "studio_executable": str(self.studio_executable) if self.studio_executable else None,
            "resources_dir": str(self.resources_dir) if self.resources_dir else None,
            "data_dir": str(self.data_dir) if self.data_dir else None,
            "jobs_dir": str(self.jobs_dir),
            "timeout_seconds": self.timeout_seconds,
            "config_file": str(self.config_file) if self.config_file else None,
            "sources": self.sources,
        }


def find_config_file(start: Path | None = None) -> Path | None:
    env = os.environ.get("BAMBU_BUTLER_CONFIG")
    if env:
        return Path(env).expanduser()
    here = (start or Path.cwd()).resolve()
    for directory in [here, *here.parents]:
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def read_config_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Konfigurationsdatei nicht gefunden: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Konfigurationsdatei ist kein gültiges JSON: {path} ({exc})") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"Konfigurationsdatei muss ein JSON-Objekt enthalten: {path}")
    return data


def load_settings(overrides: dict | None = None, *, config_path: Path | None = None,
                  autodetect: bool = True) -> Settings:
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    config_path = config_path or find_config_file()
    file_values: dict = read_config_file(config_path) if config_path else {}
    base_dir = config_path.parent if config_path else Path.cwd()

    settings = Settings(config_file=config_path)

    for key in ("studio_executable", "resources_dir", "data_dir", "jobs_dir", "timeout_seconds"):
        value, source = None, None
        if key in overrides:
            value, source = overrides[key], "cli"
        elif os.environ.get(ENV[key]):
            value, source = os.environ[ENV[key]], f"env:{ENV[key]}"
        elif file_values.get(key) not in (None, ""):
            value, source = file_values[key], "config"
        if value is None:
            continue
        if key == "timeout_seconds":
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"timeout_seconds muss eine ganze Zahl sein, nicht {value!r}") from exc
            if value <= 0:
                raise ConfigError("timeout_seconds muss größer als 0 sein")
        else:
            value = Path(str(value)).expanduser()
            if source == "config" and not value.is_absolute():
                value = base_dir / value
        setattr(settings, key, value)
        settings.sources[key] = source

    if autodetect:
        if settings.studio_executable is None:
            found = platforms.find_executable()
            if found:
                settings.studio_executable = found
                settings.sources["studio_executable"] = "auto"
        if settings.resources_dir is None:
            found = platforms.find_resources(settings.studio_executable)
            if found:
                settings.resources_dir = found
                settings.sources["resources_dir"] = "auto"
        if settings.data_dir is None:
            found = platforms.find_data_dir()
            if found:
                settings.data_dir = found
                settings.sources["data_dir"] = "auto"
    settings.sources.setdefault("jobs_dir", "default")
    settings.sources.setdefault("timeout_seconds", "default")
    return settings


def default_config_dict(settings: Settings) -> dict:
    return {
        "$comment": "Bambu Butler configuration. Empty values are auto-detected. "
                    "Environment variables BAMBU_BUTLER_* override these values.",
        "studio_executable": str(settings.studio_executable) if settings.studio_executable else "",
        "resources_dir": str(settings.resources_dir) if settings.resources_dir else "",
        "data_dir": str(settings.data_dir) if settings.data_dir else "",
        "jobs_dir": "jobs",
        "timeout_seconds": DEFAULT_TIMEOUT,
    }
