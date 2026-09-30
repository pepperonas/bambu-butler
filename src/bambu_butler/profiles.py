"""Reading, indexing and resolving Bambu Studio profiles (presets).

The inheritance rules mirror ``PresetBundle::load_vendor_configs_from_json`` in
BambuStudio (v02.08): a profile starts from its resolved ``inherits`` parent,
then the configs named in ``include`` are applied, then its own keys.

The Bambu Studio CLI does *not* resolve inheritance for files passed via
``--load-settings`` / ``--load-filaments``; they must be complete and carry
``type``, ``name`` and ``from`` (``system`` or ``User``). ``export_for_cli``
produces such files.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import InheritanceCycleError, ProfileError, ProfileNotFoundError

PROFILE_TYPES = ("machine", "process", "filament")

# Keys describing the preset itself, not print settings.
META_KEYS = frozenset({
    "type", "name", "inherits", "from", "setting_id", "instantiation", "include", "version",
    "description", "base_id", "user_id", "updated_time", "is_custom_defined", "renamed_from",
    "alias", "filament_id", "url",
})

# Machine keys the Bambu CLI refuses to see modified (CLI_MODIFIED_PARAMS_TO_PRINTER).
LOCKED_MACHINE_KEYS = frozenset({"printable_area", "printable_height", "bed_exclude_area"})


@dataclass
class ProfileRecord:
    name: str
    type: str | None
    origin: str  # "system" or "user"
    vendor: str | None
    path: Path
    raw: dict[str, Any]

    @property
    def inherits(self) -> str | None:
        value = self.raw.get("inherits")
        return value or None

    @property
    def instantiable(self) -> bool:
        value = str(self.raw.get("instantiation", "")).lower()
        if self.origin == "user":
            return value != "false"
        return value == "true"

    @property
    def includes(self) -> list[str]:
        value = self.raw.get("include")
        if not value:
            return []
        if isinstance(value, str):
            return [value]
        return [str(v) for v in value]

    def summary(self) -> dict:
        data = {
            "name": self.name,
            "type": self.type,
            "origin": self.origin,
            "vendor": self.vendor,
            "instantiable": self.instantiable,
            "inherits": self.inherits,
            "path": str(self.path),
        }
        return data


@dataclass
class ResolvedProfile:
    record: ProfileRecord
    values: dict[str, Any]
    chain: list[str]
    system_name: str | None  # nearest instantiable system ancestor (or itself)
    filament_id: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.record.name

    @property
    def type(self) -> str | None:
        return self.record.type

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def first(self, key: str, default: Any = None) -> Any:
        value = self.values.get(key, default)
        if isinstance(value, list):
            return value[0] if value else default
        return value

    def compatible_printers(self) -> list[str]:
        value = self.values.get("compatible_printers") or []
        return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def _read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


class ProfileStore:
    """Index of system and user profiles from one or more directories."""

    def __init__(self) -> None:
        self.system: dict[tuple[str, str], ProfileRecord] = {}
        self.user: dict[str, ProfileRecord] = {}
        self.load_errors: list[str] = []
        self.sources: list[dict] = []

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, resources_dir: Path | None, data_dir: Path | None) -> ProfileStore:
        store = cls()
        if resources_dir:
            store.add_system_root(resources_dir / "profiles", label="resources")
        if data_dir:
            # Bambu Studio keeps (possibly newer) copies of the system profiles here.
            store.add_system_root(data_dir / "system", label="data_dir/system")
            store.add_user_root(data_dir / "user")
        return store

    def add_system_root(self, root: Path, *, label: str) -> None:
        if not root.is_dir():
            return
        vendors = [p for p in sorted(root.iterdir()) if p.is_dir()]
        count = 0
        for vendor_dir in vendors:
            for ptype in PROFILE_TYPES:
                type_dir = vendor_dir / ptype
                if not type_dir.is_dir():
                    continue
                for path in sorted(type_dir.rglob("*.json")):
                    data = _read_json(path)
                    if data is None:
                        self.load_errors.append(f"Nicht lesbares Profil: {path}")
                        continue
                    name = str(data.get("name") or path.stem)
                    record = ProfileRecord(name, str(data.get("type") or ptype), "system",
                                           vendor_dir.name, path, data)
                    self.system[(vendor_dir.name, name)] = record  # later roots win
                    count += 1
        self.sources.append({"label": label, "path": str(root), "profiles": count})

    def add_user_root(self, root: Path) -> None:
        if not root.is_dir():
            return
        count = 0
        for account_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            for ptype in PROFILE_TYPES:
                type_dir = account_dir / ptype
                if not type_dir.is_dir():
                    continue
                for path in sorted(type_dir.glob("*.json")):  # not recursive: skip "base/"
                    data = _read_json(path)
                    if data is None:
                        self.load_errors.append(f"Nicht lesbares Profil: {path}")
                        continue
                    name = str(data.get("name") or path.stem)
                    record = ProfileRecord(name, str(data.get("type") or ptype), "user", None, path, data)
                    if name in self.user and self.user[name].path != path:
                        self.load_errors.append(f"Benutzerprofil doppelt vorhanden, verwende {path}: {name}")
                    self.user[name] = record
                    count += 1
        self.sources.append({"label": "data_dir/user", "path": str(root), "profiles": count})

    # ------------------------------------------------------------------ lookup
    def all_records(self) -> list[ProfileRecord]:
        return list(self.system.values()) + list(self.user.values())

    def find(self, name: str, *, vendor: str | None = None, ptype: str | None = None) -> ProfileRecord:
        candidates: list[ProfileRecord] = []
        if name in self.user:
            candidates.append(self.user[name])
        if vendor and (vendor, name) in self.system:
            candidates.append(self.system[(vendor, name)])
        if not candidates:
            candidates = [r for (v, n), r in self.system.items() if n == name]
            # Prefer the Bambu Lab vendor when a base name exists in several vendors.
            candidates.sort(key=lambda r: (r.vendor != "BBL", r.vendor or ""))
        if ptype:
            typed = [r for r in candidates if r.type == ptype]
            if not typed and candidates:
                raise ProfileError(
                    f"Profil '{name}' hat den Typ '{candidates[0].type}', erwartet wurde '{ptype}'.")
            candidates = typed
        if not candidates:
            raise ProfileNotFoundError(
                f"Profil nicht gefunden: '{name}'" + (f" (Typ {ptype})" if ptype else ""),
                hint="Mit 'bambu-butler profiles list' verfügbare Profile anzeigen.",
            )
        return candidates[0]

    def list(self, *, ptype: str | None = None, include_abstract: bool = False,
             vendor: str | None = None, query: str | None = None) -> list[ProfileRecord]:
        records = self.all_records()
        out = []
        q = query.lower() if query else None
        for r in records:
            if ptype and r.type != ptype:
                continue
            if not include_abstract and not r.instantiable:
                continue
            if vendor and r.origin == "system" and r.vendor != vendor:
                continue
            if q and q not in r.name.lower():
                continue
            out.append(r)
        out.sort(key=lambda r: (r.type or "", r.origin != "user", r.name.lower()))
        return out

    # ------------------------------------------------------------------ resolution
    def resolve(self, record_or_name: ProfileRecord | str, *, ptype: str | None = None) -> ResolvedProfile:
        record = (record_or_name if isinstance(record_or_name, ProfileRecord)
                  else self.find(record_or_name, ptype=ptype))
        return self._resolve(record, stack=[])

    def _resolve(self, record: ProfileRecord, stack: list[str]) -> ResolvedProfile:
        key = f"{record.origin}:{record.vendor}:{record.name}"
        if key in stack:
            cycle = [s.split(":", 2)[2] for s in stack[stack.index(key):]] + [record.name]
            raise InheritanceCycleError("Zyklische Profilvererbung: " + " -> ".join(cycle),
                                        details={"cycle": cycle})
        stack = [*stack, key]
        warnings: list[str] = []

        values: dict[str, Any] = {}
        chain: list[str] = []
        system_name: str | None = None
        filament_id: str | None = None
        if record.inherits:
            try:
                parent_record = self.find(record.inherits, vendor=record.vendor)
            except ProfileNotFoundError as exc:
                raise ProfileNotFoundError(
                    f"Elternprofil '{record.inherits}' von '{record.name}' fehlt.",
                    hint="Bambu Studio aktualisieren oder das Profil in Bambu Studio neu speichern.",
                    details={"profile": record.name, "missing_parent": record.inherits},
                ) from exc
            parent = self._resolve(parent_record, stack)
            values = copy.deepcopy(parent.values)
            chain = parent.chain
            system_name = parent.system_name
            filament_id = parent.filament_id
            warnings.extend(parent.warnings)

        for include_name in record.includes:
            try:
                include = self.find(include_name, vendor=record.vendor)
            except ProfileNotFoundError:
                warnings.append(f"Include '{include_name}' von '{record.name}' nicht gefunden.")
                continue
            for k, v in include.raw.items():
                if k not in META_KEYS:
                    values[k] = copy.deepcopy(v)

        for k, v in record.raw.items():
            if k not in META_KEYS:
                values[k] = copy.deepcopy(v)
        if record.raw.get("filament_id"):
            filament_id = str(record.raw["filament_id"])
        if record.origin == "system" and record.instantiable:
            system_name = record.name
        return ResolvedProfile(record, values, [*chain, record.name], system_name, filament_id, warnings)

    # ------------------------------------------------------------------ compatibility
    @staticmethod
    def compatibility(profile: ResolvedProfile, printer: ResolvedProfile) -> tuple[bool | None, str]:
        """Return (compatible, reason). ``None`` means it cannot be decided locally."""
        listed = profile.compatible_printers()
        names = {printer.name, printer.system_name} - {None}
        condition = str(profile.get("compatible_printers_condition") or "").strip()
        if listed:
            if names & set(listed):
                return True, "Drucker ist in compatible_printers aufgeführt."
            return False, (f"'{profile.name}' ist laut compatible_printers nicht für "
                           f"'{printer.system_name or printer.name}' freigegeben.")
        if condition:
            return None, f"Kompatibilität hängt von einer Bedingung ab, die lokal nicht ausgewertet wird: {condition}"
        return True, "Keine Einschränkung (compatible_printers ist leer)."


def export_for_cli(resolved: ResolvedProfile, *, name: str | None = None,
                   overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a complete profile JSON that ``--load-settings``/``--load-filaments`` accept."""
    if resolved.type not in PROFILE_TYPES:
        raise ProfileError(f"Profil '{resolved.name}' hat keinen gültigen Typ ({resolved.type}).")
    values = copy.deepcopy(resolved.values)
    overrides = overrides or {}
    values.update(copy.deepcopy(overrides))
    unchanged_system = (not overrides and name is None and resolved.record.origin == "system")
    header: dict[str, Any] = {"type": resolved.type}
    if unchanged_system:
        header.update({"name": resolved.name, "from": "system", "instantiation": "true"})
        if resolved.record.raw.get("setting_id"):
            header["setting_id"] = resolved.record.raw["setting_id"]
    else:
        if not resolved.system_name:
            raise ProfileError(
                f"'{resolved.name}' hat kein Systemprofil als Vorfahren; die Bambu-CLI benötigt es "
                "für Kompatibilitätsprüfungen.")
        header.update({"name": name or resolved.name, "from": "User", "inherits": resolved.system_name,
                       "instantiation": "true"})
    if resolved.type == "filament" and resolved.filament_id:
        header["filament_id"] = resolved.filament_id
    header.update(values)
    return header


def diff_values(base: dict[str, Any], new: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    for key in sorted(set(base) | set(new)):
        if key in META_KEYS:
            continue
        if base.get(key) != new.get(key):
            changes.append({"key": key, "before": base.get(key), "after": new.get(key)})
    return changes
