"""Typer command line interface. User-facing output is German; ``--json`` is machine-readable."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__, gui_macos, jobs, mesh, opener, printer, studio
from . import plan as plan_mod
from .errors import ButlerError, ConfigError
from .mapping import VERIFIED_AGAINST
from .platforms import current_os
from .profiles import PROFILE_TYPES, ProfileStore
from .settings import CONFIG_FILENAME, Settings, default_config_dict, load_settings
from .validate import require_ready, validate_plan

app = typer.Typer(
    name="bambu-butler",
    help="Bambu Butler: Druckaufträge als geprüfte Pläne vorbereiten und mit Bambu Studio slicen.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)
profiles_app = typer.Typer(help="Drucker-, Prozess- und Filamentprofile anzeigen.", no_args_is_help=True)
printer_app = typer.Typer(help="Direkte Druckersteuerung (in 0.0.1 nicht implementiert).", no_args_is_help=True)
gui_app = typer.Typer(help="Optionaler macOS-GUI-Adapter.", no_args_is_help=True)
app.add_typer(profiles_app, name="profiles")
app.add_typer(printer_app, name="printer")
app.add_typer(gui_app, name="gui")

console = Console()
err_console = Console(stderr=True)


@dataclass
class State:
    json: bool = False
    overrides: dict | None = None
    config: Path | None = None
    _settings: Settings | None = None

    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = load_settings(self.overrides, config_path=self.config)
        return self._settings


state = State()


def emit(data: dict, render=None) -> None:
    if state.json:
        sys.stdout.write(json.dumps({"ok": True, **data}, ensure_ascii=False, indent=2, default=str) + "\n")
    elif render:
        render()


def fail(exc: ButlerError) -> None:
    if state.json:
        sys.stdout.write(json.dumps({"ok": False, "error": exc.to_dict()}, ensure_ascii=False, indent=2,
                                    default=str) + "\n")
    else:
        err_console.print(f"[bold red]Fehler:[/] {exc.message}")
        if exc.hint:
            err_console.print(f"[yellow]Hinweis:[/] {exc.hint}")
        issues = exc.details.get("issues") if exc.details else None
        if issues:
            for issue in issues:
                if isinstance(issue, dict) and issue.get("level") in ("error", None):
                    err_console.print(f"  - {issue.get('location', '')}{issue['message']}")
    raise typer.Exit(exc.exit_code)


def guarded(fn):
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ButlerError as exc:
            fail(exc)

    return wrapper


def version_callback(value: bool) -> None:
    if value:
        console.print(f"bambu-butler {__version__}")
        raise typer.Exit()


@app.callback()
def main_options(
    json_output: Annotated[bool, typer.Option("--json", help="Maschinenlesbare JSON-Ausgabe.")] = False,
    studio_path: Annotated[Path | None, typer.Option("--studio", help="Pfad zur Bambu-Studio-Executable.")] = None,
    resources: Annotated[Path | None, typer.Option("--resources", help="Bambu-Studio-Ressourcenordner.")] = None,
    data_dir: Annotated[Path | None, typer.Option("--data-dir", help="Bambu-Studio-Datenordner.")] = None,
    jobs_dir: Annotated[Path | None, typer.Option("--jobs-dir", help="Ordner für Aufträge.")] = None,
    config: Annotated[Path | None, typer.Option("--config", help=f"Pfad zu {CONFIG_FILENAME}.")] = None,
    version: Annotated[bool, typer.Option("--version", callback=version_callback, is_eager=True,
                                          help="Version anzeigen.")] = False,
) -> None:
    state.json = json_output
    state.config = config
    state.overrides = {"studio_executable": studio_path, "resources_dir": resources, "data_dir": data_dir,
                       "jobs_dir": jobs_dir}
    state._settings = None


def _store(settings: Settings) -> ProfileStore:
    if not settings.resources_dir and not settings.data_dir:
        raise ConfigError("Keine Profilquelle gefunden (weder Ressourcen- noch Datenordner von Bambu Studio).",
                          hint="Bambu Studio installieren oder --resources / --data-dir angeben.")
    return ProfileStore.load(settings.resources_dir, settings.data_dir)


# ------------------------------------------------------------------------------------------ init
@app.command()
@guarded
def init(
    directory: Annotated[Path, typer.Argument(help="Arbeitsordner.")] = Path("."),
    force: Annotated[bool, typer.Option("--force", help="Bestehende Konfiguration überschreiben.")] = False,
) -> None:
    """Arbeitsordner mit Konfiguration, jobs/ und plans/ anlegen."""
    directory = directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    cfg_path = directory / CONFIG_FILENAME
    created = []
    if cfg_path.exists() and not force:
        existing = True
    else:
        existing = False
        settings = load_settings(state.overrides, config_path=None)
        cfg_path.write_text(json.dumps(default_config_dict(settings), indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
        created.append(str(cfg_path))
    for sub in ("jobs", "plans"):
        (directory / sub).mkdir(exist_ok=True)
    data = {"config_file": str(cfg_path), "config_existed": existing, "created": created,
            "directories": [str(directory / "jobs"), str(directory / "plans")]}

    def render():
        if existing:
            console.print(f"Konfiguration existiert bereits: {cfg_path} (mit --force überschreiben)")
        else:
            console.print(f"[green]Angelegt:[/] {cfg_path}")
        console.print(f"Ordner: {directory / 'jobs'}, {directory / 'plans'}")
        console.print("Nächster Schritt: [bold]bambu-butler doctor[/]")

    emit(data, render)


# ------------------------------------------------------------------------------------------ doctor
@app.command()
@guarded
def doctor(
    strict: Annotated[bool, typer.Option("--strict", help="Exit-Code 3, wenn nicht geslict werden kann.")] = False,
) -> None:
    """Installation, CLI-Funktionen und Profile prüfen."""
    settings = state.settings()
    info = studio.detect(settings.studio_executable, timeout=min(60, settings.timeout_seconds))
    store = None
    counts: dict[str, dict[str, int]] = {}
    store_problem = None
    try:
        store = _store(settings)
        for t in PROFILE_TYPES:
            recs = store.list(ptype=t)
            counts[t] = {"system": sum(r.origin == "system" for r in recs),
                         "user": sum(r.origin == "user" for r in recs)}
    except ButlerError as exc:
        store_problem = exc.message
    missing = []
    if not info.exists:
        missing.append("Bambu Studio (Executable)")
    elif not info.cli_usable:
        missing.append("Nutzbare Bambu-Studio-CLI")
    if store_problem or not counts or not any(c["system"] for c in counts.values()):
        missing.append("Systemprofile von Bambu Studio")
    printers = [r.name for r in store.list(ptype="machine")] if store else []
    data = {
        "bambu_butler_version": __version__,
        "os": current_os(),
        "python": sys.version.split()[0],
        "settings": settings.to_dict(),
        "studio": info.to_dict(),
        "profile_sources": store.sources if store else [],
        "profile_counts": counts,
        "printers": printers,
        "profile_load_errors": store.load_errors[:20] if store else [],
        "missing": missing,
        "can_prepare_profiles": bool(counts and counts.get("machine", {}).get("system")),
        "can_slice": info.cli_usable and not store_problem,
        "gui_automation": "macOS (optional)" if current_os() == "macos" else "nicht verfügbar",
        "printer_control": "nicht implementiert",
        "mapping_verified_against": VERIFIED_AGAINST,
    }

    def render():
        t = Table(title="Bambu Butler doctor", show_header=False)
        t.add_row("Version", __version__)
        t.add_row("System", f"{current_os()} / Python {data['python']}")
        t.add_row("Konfiguration", str(settings.config_file or "keine (Auto-Erkennung)"))
        t.add_row("Bambu Studio", f"{info.executable or '[red]nicht gefunden[/]'}"
                  + (f" ({settings.sources.get('studio_executable')})" if info.executable else ""))
        t.add_row("Version Bambu Studio", f"{info.version or 'unbekannt'}"
                  + (f" (aus {info.version_source})" if info.version_source else ""))
        t.add_row("CLI nutzbar", "[green]ja[/]" if info.cli_usable else "[red]nein[/]")
        t.add_row("Ressourcen", str(settings.resources_dir or "[red]nicht gefunden[/]"))
        t.add_row("Datenordner", str(settings.data_dir or "[yellow]nicht gefunden[/]"))
        for ptype, c in counts.items():
            t.add_row(f"Profile {ptype}", f"{c['system']} System, {c['user']} Benutzer")
        t.add_row("Druckerprofile", f"{len(printers)} verfügbar")
        t.add_row("Slicen möglich", "[green]ja[/]" if data["can_slice"] else "[red]nein[/]")
        t.add_row("Druckersteuerung", "nicht implementiert")
        console.print(t)
        for p in info.problems + ([store_problem] if store_problem else []):
            console.print(f"[yellow]•[/] {p}")
        if missing:
            console.print(f"[bold red]Fehlt:[/] {', '.join(missing)}")
            console.print("Pfade überschreiben: --studio, --resources, --data-dir oder bambu-butler.json")

    emit(data, render)
    if strict and not data["can_slice"]:
        raise typer.Exit(3)


# ------------------------------------------------------------------------------------------ profiles
@profiles_app.command("list")
@guarded
def profiles_list(
    ptype: Annotated[str | None, typer.Option("--type", "-t", help="machine | process | filament")] = None,
    printer_name: Annotated[str | None, typer.Option("--printer", "-p",
                                                     help="Nur mit diesem Druckerprofil kompatible.")] = None,
    query: Annotated[str | None, typer.Option("--query", "-q", help="Namensfilter (Teilstring).")] = None,
    vendor: Annotated[str | None, typer.Option("--vendor", help="Hersteller-Ordner, z. B. BBL.")] = None,
    include_abstract: Annotated[bool, typer.Option("--all", help="Auch Basis-/Vorlagenprofile.")] = False,
) -> None:
    """Profile auflisten."""
    if ptype and ptype not in PROFILE_TYPES:
        raise ButlerError(f"Unbekannter Typ '{ptype}'. Erlaubt: {', '.join(PROFILE_TYPES)}")
    store = _store(state.settings())
    records = store.list(ptype=ptype, include_abstract=include_abstract, vendor=vendor, query=query)
    compat: dict[str, str] = {}
    if printer_name:
        target = store.resolve(printer_name, ptype="machine")
        kept = []
        for r in records:
            if r.type == "machine":
                if r.name == target.name:
                    kept.append(r)
                continue
            try:
                ok, _ = store.compatibility(store.resolve(r), target)
            except ButlerError:
                continue
            if ok is not False:
                kept.append(r)
                compat[r.name] = "ja" if ok else "unklar"
        records = kept
    items = [{**r.summary(), **({"compatible": compat[r.name]} if r.name in compat else {})} for r in records]

    def render():
        t = Table(title=f"{len(items)} Profile")
        t.add_column("Typ")
        t.add_column("Name")
        t.add_column("Quelle")
        t.add_column("erbt von")
        for i in items:
            t.add_row(i["type"], i["name"], i["origin"] + (f"/{i['vendor']}" if i["vendor"] else ""),
                      i["inherits"] or "")
        console.print(t)

    emit({"count": len(items), "profiles": items}, render)


@profiles_app.command("show")
@guarded
def profiles_show(
    name: Annotated[str, typer.Argument(help="Exakter Profilname.")],
    ptype: Annotated[str | None, typer.Option("--type", "-t")] = None,
    raw: Annotated[bool, typer.Option("--raw", help="Nur die Datei, ohne Vererbung.")] = False,
    keys: Annotated[str | None, typer.Option("--keys", "-k", help="Kommagetrennte Schlüssel.")] = None,
) -> None:
    """Ein Profil vollständig aufgelöst (oder roh) anzeigen."""
    store = _store(state.settings())
    record = store.find(name, ptype=ptype)
    resolved = store.resolve(record)
    values = record.raw if raw else resolved.values
    if keys:
        wanted = [k.strip() for k in keys.split(",") if k.strip()]
        values = {k: values.get(k) for k in wanted}
    data = {"profile": record.summary(), "chain": resolved.chain, "system_name": resolved.system_name,
            "filament_id": resolved.filament_id, "warnings": resolved.warnings, "raw": raw,
            "values": values}

    def render():
        console.print(Panel(f"[bold]{record.name}[/] ({record.type}, {record.origin})\n"
                            f"Datei: {record.path}\nVererbung: {' → '.join(resolved.chain)}",
                            title="Profil"))
        t = Table(show_header=True)
        t.add_column("Schlüssel")
        t.add_column("Wert", overflow="fold")
        for k in sorted(values):
            v = values[k]
            text = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
            t.add_row(k, text if len(text) < 200 else text[:197] + "...")
        console.print(t)

    emit(data, render)


# ------------------------------------------------------------------------------------------ inspect
@app.command()
@guarded
def inspect(
    model: Annotated[Path, typer.Argument(help=".stl oder .3mf")],
    printer_name: Annotated[str | None, typer.Option("--printer", "-p", help="Druckraum dieses Profils prüfen.")]
    = None,
) -> None:
    """Modell analysieren: Maße, Einheiten, Objekte, Metadaten, Geometrie-Hinweise."""
    info = mesh.load_model(model)
    bed = height = None
    if printer_name:
        prof = _store(state.settings()).resolve(printer_name, ptype="machine")
        bed = mesh.bed_from_machine(prof.get("printable_area"))
        try:
            height = float(prof.first("printable_height"))
        except (TypeError, ValueError):
            height = None
    report = mesh.analyse(info, bed=bed, height=height)
    report["limits"] = ("Belastungsrichtung, optimale Ausrichtung und Supportbedarf lassen sich aus dem Mesh "
                        "nicht sicher bestimmen.")

    def render():
        bb = report.get("bounding_box_mm", {})
        t = Table(title=f"Modell: {info.path.name}", show_header=False)
        t.add_row("Format", report["format"])
        t.add_row("Einheit", str(report["unit"]))
        t.add_row("Objekte", str(report["object_count"]))
        if bb:
            t.add_row("Größe (X × Y × Z)", " × ".join(f"{v:.2f}" for v in bb["size"]) + " mm")
        topo = report.get("topology", {})
        if topo:
            t.add_row("Dreiecke", str(topo["triangles"]))
            t.add_row("Geschlossen", "ja" if topo["watertight"] else "nein")
        if report.get("fit"):
            f = report["fit"]
            t.add_row("Passt in Druckraum", ("[green]ja[/]" if f["fits"] else "[red]nein[/]")
                      + f" ({' × '.join(str(v) for v in f['bed_mm'])} mm)")
        console.print(t)
        if report["object_count"] > 1 or info.format == "3mf":
            ot = Table(title="Objekte")
            for col in ("Name", "Dreiecke", "Größe mm", "Filament-Slot"):
                ot.add_column(col)
            for o in report["objects"]:
                ot.add_row(o["name"], str(o["triangles"]), " × ".join(f"{v:.1f}" for v in o["size_mm"]),
                           str(o.get("filament_slot", "–")))
            console.print(ot)
        if info.project:
            console.print(f"Projekt: {json.dumps(info.project, ensure_ascii=False)}")
        for w in report["warnings"]:
            console.print(f"[yellow]•[/] {w}")
        console.print(f"[dim]{report['limits']}[/]")

    emit({"model": report}, render)


# ------------------------------------------------------------------------------------------ plans
def _render_issues(result) -> None:
    for i in result.issues:
        color = {"error": "red", "warning": "yellow", "info": "blue"}[i.level]
        console.print(f"[{color}]{i.level:>7}[/] {i.message}")


@app.command()
@guarded
def validate(plan_path: Annotated[Path, typer.Argument(help="Druckplan (JSON).")]) -> None:
    """Plan prüfen: Schema und Kompatibilität mit den vorhandenen Profilen."""
    plan = plan_mod.load_plan(plan_path)
    result = validate_plan(plan, plan_path.resolve(), _store(state.settings()))
    data = {"validation": result.to_dict()}

    def render():
        console.print("[green]✓[/] Schema-gültig (print-plan v1)")
        if result.compatible:
            console.print("[green]✓[/] Kompatibel mit den vorhandenen Profilen")
        else:
            console.print("[red]✗[/] Nicht kompatibel mit den vorhandenen Profilen")
        console.print("[dim]•[/] Geslict: nein (erst nach 'bambu-butler slice')")
        _render_issues(result)
        if result.process_overrides:
            console.print("Prozess-Änderungen: " + ", ".join(
                f"{k}={v}" for k, v in result.process_overrides.items()))

    emit(data, render)
    if not result.compatible:
        raise typer.Exit(2)


def _run_job(plan_path: Path, mode: str, dry_run: bool, timeout: int | None, allow_open: bool) -> None:
    settings = state.settings()
    raw = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.is_file() else None
    plan = plan_mod.load_plan(plan_path)
    result = validate_plan(plan, plan_path.resolve(), _store(settings))
    require_ready(result, allow_open_questions=allow_open)
    info = studio.detect(settings.studio_executable, timeout=min(60, settings.timeout_seconds))
    job = jobs.plan_job(result, settings, mode=mode)
    try:
        job = jobs.execute(job, settings, info, raw, dry_run=dry_run, timeout=timeout)
    except ButlerError:
        if not state.json:
            console.print(f"Auftragsordner: {job.job_dir}")
        raise
    data = {"job": job.to_dict()}

    def render():
        color = "green" if job.status in ("sliced", "prepared") else "yellow"
        console.print(Panel(jobs.STATUS_TEXT[job.status], title=f"Status: {job.status}", border_style=color))
        for key, changes in job.changes.items():
            for c in changes:
                console.print(f"  {key}.{c['key']}: {jobs._fmt(c['before'])} → {jobs._fmt(c['after'])}")
        if dry_run:
            console.print("Geplanter Aufruf (Argumentliste):")
            console.print(json.dumps(job.argv, ensure_ascii=False, indent=1))
            console.print(f"Auftragsordner (würde angelegt): {job.job_dir}")
        else:
            console.print(f"Auftragsordner: {job.job_dir}")
            console.print(f"Bericht: {job.job_dir / job.files['report_md']}")
        if job.slice_summary:
            s = job.slice_summary
            console.print(f"Druckzeit: {jobs.slicer.format_duration(s.get('print_time_seconds'))}, "
                          f"Filament: {s.get('filament_g', 'unbekannt')} g (Quelle: {s['source']})")
        for n in job.notes:
            console.print(f"[yellow]•[/] {n}")
        _render_issues(result)
        console.print("[dim]Es wurde kein Druck gestartet.[/]")

    emit(data, render)


@app.command()
@guarded
def prepare(
    plan_path: Annotated[Path, typer.Argument(help="Druckplan (JSON).")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Nur anzeigen, nichts schreiben/ausführen.")] = False,
    timeout: Annotated[int | None, typer.Option("--timeout", help="Sekunden bis zum Abbruch.")] = None,
    allow_open_questions: Annotated[bool, typer.Option("--allow-open-questions")] = False,
) -> None:
    """Auftragsordner mit Profilen anlegen und ein (ungeslictes) 3MF-Projekt exportieren."""
    _run_job(plan_path, "prepare", dry_run, timeout, allow_open_questions)


@app.command("slice")
@guarded
def slice_(
    plan_path: Annotated[Path, typer.Argument(help="Druckplan (JSON).")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Nur anzeigen, nichts schreiben/ausführen.")] = False,
    timeout: Annotated[int | None, typer.Option("--timeout", help="Sekunden bis zum Abbruch.")] = None,
    allow_open_questions: Annotated[bool, typer.Option("--allow-open-questions")] = False,
) -> None:
    """Vorbereiten und mit der Bambu-Studio-CLI slicen. Startet niemals einen Druck."""
    _run_job(plan_path, "slice", dry_run, timeout, allow_open_questions)


@app.command("open")
@guarded
def open_(
    project: Annotated[Path, typer.Argument(help=".3mf-Projekt")],
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    check_gui: Annotated[bool, typer.Option("--check-gui", help="macOS: Fenster/Berechtigungen prüfen.")] = False,
) -> None:
    """Projekt in Bambu Studio öffnen (Betriebssystemfunktion)."""
    settings = state.settings()
    data = opener.open_project(project, settings.studio_executable, dry_run=dry_run)
    if check_gui and not dry_run:
        import time

        time.sleep(3)
        data["gui"] = gui_macos.check(expected_file=project.stem).to_dict()
    data["manual_next_steps"] = [gui_macos.MANUAL_STEPS["dialog"], gui_macos.MANUAL_STEPS["send"]]

    def render():
        if dry_run:
            console.print(f"Würde ausführen: {data['argv']}")
        else:
            console.print(f"[green]Geöffnet:[/] {data['project']}")
        for p in data.get("gui", {}).get("problems", []):
            console.print(f"[yellow]•[/] {p}")
        console.print("Druck bitte manuell in Bambu Studio prüfen und starten.")

    emit(data, render)


@app.command()
@guarded
def schema(output: Annotated[Path | None, typer.Option("--output", "-o")] = None) -> None:
    """JSON-Schema des Druckplans (v1) ausgeben."""
    s = plan_mod.json_schema()
    text = json.dumps(s, indent=2, ensure_ascii=False) + "\n"
    if output:
        output.write_text(text, encoding="utf-8")
        emit({"written": str(output)}, lambda: console.print(f"Geschrieben: {output}"))
    else:
        sys.stdout.write(text)


@app.command()
@guarded
def template(
    model: Annotated[Path, typer.Argument(help=".stl oder .3mf")],
    printer_name: Annotated[str, typer.Option("--printer", "-p")],
    process_name: Annotated[str | None, typer.Option("--process")] = None,
    filament_name: Annotated[list[str] | None, typer.Option("--filament", "-f")] = None,
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Planvorlage mit Standardprofilen des Druckers erzeugen."""
    store = _store(state.settings())
    prn = store.resolve(printer_name, ptype="machine")
    process_name = process_name or prn.get("default_print_profile")
    fils = filament_name or prn.get("default_filament_profile") or []
    if isinstance(fils, str):
        fils = [fils]
    if not process_name or not fils:
        raise ButlerError("Drucker nennt keine Standardprofile; --process und --filament angeben.")
    model_ref = str(model)
    if output:
        import os

        try:
            model_ref = Path(os.path.relpath(Path(model).resolve(), output.resolve().parent)).as_posix()
        except ValueError:  # different drives on Windows
            model_ref = str(Path(model).resolve())
    plan = {
        "schema": "bambu-butler/print-plan",
        "schema_version": "1",
        "request": "",
        "model": {"path": model_ref},
        "printer": {"profile": prn.name, "nozzle_diameter_mm": float(prn.first("nozzle_diameter") or 0) or None},
        "process": {"profile": process_name},
        "filaments": [{"profile": f} for f in fils],
        "settings": {"quality": {}, "strength": {}, "support": {}, "adhesion": {}},
        "overrides": {"process": {}, "filament": {}, "machine": {}},
        "transform": {"rotate_x_deg": 0, "rotate_y_deg": 0, "rotate_z_deg": 0, "scale": 1.0,
                      "auto_orient": False, "arrange": True},
        "output": {"job_name": jobs.slugify(Path(model).stem)},
        "assumptions": [],
        "rationale": [],
        "open_questions": [],
    }
    plan_mod.parse_plan(plan)
    text = json.dumps(plan, indent=2, ensure_ascii=False) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        emit({"written": str(output), "plan": plan}, lambda: console.print(f"Plan geschrieben: {output}"))
    else:
        emit({"plan": plan}, lambda: sys.stdout.write(text))


# ------------------------------------------------------------------------------------------ printer/gui
@printer_app.command("status")
@guarded
def printer_status() -> None:
    """Stand der Druckersteuerung anzeigen."""
    emit({"implemented": False, "capabilities": printer.CAPABILITIES,
          "message": printer.NotImplementedAdapter.MESSAGE},
         lambda: console.print(printer.NotImplementedAdapter.MESSAGE))


@printer_app.command("start")
@guarded
def printer_start(project: Annotated[Path, typer.Argument()]) -> None:
    """Nicht implementiert. Startet keinen Druck."""
    printer.NotImplementedAdapter().start_print(str(project), printer.PrintConfirmation("", "", False))


@gui_app.command("check")
@guarded
def gui_check(expected: Annotated[str | None, typer.Option("--expect")] = None) -> None:
    """macOS: Berechtigungen und Bambu-Studio-Fenster prüfen (keine Klicks)."""
    info = gui_macos.check(expected)
    data: dict[str, Any] = info.to_dict()
    emit(data, lambda: [console.print(f"{k}: {v}") for k, v in data.items()])


def main() -> None:
    app()


if __name__ == "__main__":
    main()
