"""Job orchestration: plan -> job folder -> (optional) Bambu Studio CLI run -> report."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import __version__, process, slicer
from .errors import SlicerError, SlicerTimeoutError, StudioNotFoundError
from .plan import PrintPlan
from .profiles import ResolvedProfile, diff_values, export_for_cli
from .settings import Settings
from .studio import StudioInfo
from .validate import ValidationResult

STATUS_TEXT = {
    "dry_run": "Dry-Run: nichts geschrieben, nichts ausgeführt.",
    "prepared_without_studio": "Profile und Aufruf vorbereitet. Bambu Studio fehlt, kein 3MF erzeugt.",
    "prepared": "3MF-Projekt vorbereitet (nicht geslict).",
    "sliced": "Erfolgreich von Bambu Studio geslict.",
    "failed": "Bambu Studio hat einen Fehler gemeldet.",
    "timeout": "Bambu Studio hat das Zeitlimit überschritten.",
}


def slugify(text: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip()).strip("-._")
    return (slug or "job")[:48]


@dataclass
class Job:
    plan: PrintPlan
    validation: ValidationResult
    job_dir: Path
    slug: str
    mode: str  # prepare | slice
    files: dict[str, str] = field(default_factory=dict)
    profiles: dict[str, Any] = field(default_factory=dict)
    changes: dict[str, list] = field(default_factory=dict)
    argv: list[str] = field(default_factory=list)
    status: str = "planned"
    run: dict | None = None
    exit: dict | None = None
    slice_summary: dict | None = None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "status_text": STATUS_TEXT.get(self.status, self.status),
            "stages": {
                "schema_valid": True,
                "compatible_with_profiles": self.validation.compatible,
                "project_exported": self.status in ("prepared", "sliced"),
                "sliced": self.status == "sliced",
            },
            "mode": self.mode,
            "job_dir": str(self.job_dir),
            "files": self.files,
            "profiles": self.profiles,
            "changes": self.changes,
            "command": self.argv,
            "run": self.run,
            "exit": self.exit,
            "result": self.slice_summary,
            "issues": [i.to_dict() for i in self.validation.issues],
            "notes": self.notes,
            "print_started": False,
        }


def _profile_name(base: ResolvedProfile, slug: str) -> str:
    return f"{base.name} [bambu-butler {slug}]"


def plan_job(validation: ValidationResult, settings: Settings, *, mode: str, now: datetime | None = None) -> Job:
    plan = validation.plan
    now = now or datetime.now()
    slug = slugify(plan.output.job_name or validation.model_path.stem)
    jobs_root = Path(plan.output.directory).expanduser() if plan.output.directory else settings.jobs_dir
    if not jobs_root.is_absolute():
        base = settings.config_file.parent if settings.config_file else Path.cwd()
        jobs_root = base / jobs_root
    job_dir = jobs_root / f"{now:%Y%m%d-%H%M%S}-{slug}"
    job = Job(plan, validation, job_dir, slug, mode)

    printer, process_, filaments = validation.printer, validation.process, validation.filaments
    assert printer and process_ and filaments  # guaranteed by require_ready
    exports: dict[str, tuple[ResolvedProfile, dict]] = {
        "machine": (printer, validation.machine_overrides),
        "process": (process_, validation.process_overrides),
    }
    for i, fil in enumerate(filaments, start=1):
        exports[f"filament_{i}"] = (fil, validation.filament_overrides)
    job.profiles = {}
    for key, (resolved, overrides) in exports.items():
        exported = export_for_cli(resolved, name=_profile_name(resolved, slug) if overrides else None,
                                  overrides=overrides)
        job.profiles[key] = {"base": resolved.name, "base_chain": resolved.chain, "name": exported["name"],
                             "from": exported["from"], "data": exported}
        job.changes[key] = [
            {**c, "source": validation.override_sources.get(
                f"{'filament' if key.startswith('filament') else key}.{c['key']}")}
            for c in diff_values(resolved.values, {k: v for k, v in exported.items()})
        ]
    job.files = {
        "plan": "plan.json",
        "machine_profile": "profiles/machine.json",
        "process_profile": "profiles/process.json",
        **{f"filament_profile_{i}": f"profiles/filament_{i}.json" for i in range(1, len(filaments) + 1)},
        "changes": "changes.json",
        "input_model": f"input/{validation.model_path.name}",
        "command": "command.json",
        "log": "cli.log",
        "report_md": "report.md",
        "report_json": "report.json",
        "project": f"{slug}.3mf" if mode == "slice" else f"{slug}.prepared.3mf",
    }
    return job


def build_argv(job: Job, executable: Path) -> list[str]:
    d = job.job_dir
    filaments = [d / job.files[k] for k in sorted(job.files) if k.startswith("filament_profile_")]
    return slicer.build_command(
        executable,
        model=d / job.files["input_model"],
        machine=d / job.files["machine_profile"],
        process=d / job.files["process_profile"],
        filaments=filaments,
        outputdir=d,
        export_name=job.files["project"],
        slice_plates=job.mode == "slice",
        transform=job.plan.transform,
    )


def write_job_files(job: Job, plan_raw: dict) -> None:
    d = job.job_dir
    (d / "profiles").mkdir(parents=True, exist_ok=False)
    (d / "input").mkdir()
    _write_json(d / job.files["plan"], plan_raw)
    for key, info in job.profiles.items():
        _write_json(d / "profiles" / f"{key}.json", info["data"])
    _write_json(d / job.files["changes"], job.changes)
    shutil.copy2(job.validation.model_path, d / job.files["input_model"])


def execute(job: Job, settings: Settings, studio: StudioInfo, plan_raw: dict, *, dry_run: bool,
            timeout: int | None = None) -> Job:
    timeout = timeout or settings.timeout_seconds
    executable = studio.executable or Path("bambu-studio")
    job.argv = build_argv(job, executable)
    if dry_run:
        job.status = "dry_run"
        if not studio.cli_usable:
            job.notes.append("Bambu Studio ist nicht nutzbar; ein echter Lauf würde nur Profile vorbereiten.")
        return job

    write_job_files(job, plan_raw)
    command = {"argv": job.argv, "cwd": str(job.job_dir), "timeout_seconds": timeout,
               "bambu_butler_version": __version__, "studio_version": studio.version}
    _write_json(job.job_dir / job.files["command"], command)

    if not studio.cli_usable:
        job.status = "prepared_without_studio"
        job.notes.extend(studio.problems or ["Bambu Studio ist nicht verfügbar."])
        (job.job_dir / job.files["log"]).write_text("Bambu Studio wurde nicht ausgeführt.\n", encoding="utf-8")
        write_reports(job)
        if job.mode == "slice":
            raise StudioNotFoundError(
                "Slicen nicht möglich: Bambu Studio ist nicht installiert oder die CLI ist nicht nutzbar. "
                f"Profile und Aufruf liegen in {job.job_dir}.",
                hint="'bambu-butler doctor' ausführen oder --studio PFAD angeben.",
                details={"job_dir": str(job.job_dir)})
        return job

    try:
        result = process.run(job.argv, timeout=timeout, cwd=job.job_dir)
    except OSError as exc:
        job.status = "failed"
        job.exit = {"code": None, "name": "OS_ERROR", "message": str(exc)}
        write_reports(job)
        raise SlicerError(f"Bambu Studio konnte nicht gestartet werden: {exc}",
                          details={"job_dir": str(job.job_dir)}) from exc
    job.run = result.to_dict()
    log = [f"$ {json.dumps(job.argv, ensure_ascii=False)}", f"returncode: {result.returncode}",
           f"timed_out: {result.timed_out}", "", "--- stdout ---", result.stdout, "", "--- stderr ---",
           result.stderr]
    (job.job_dir / job.files["log"]).write_text("\n".join(log), encoding="utf-8")

    job.exit = slicer.describe_exit(result.returncode)
    result_json = slicer.read_result_json(job.job_dir)
    project = job.job_dir / job.files["project"]
    if result.timed_out:
        job.status = "timeout"
    elif result.returncode == 0 and project.is_file():
        if job.mode == "slice":
            info = slicer.read_slice_info(project)
            job.slice_summary = slicer.summarize_slice(result_json, info)
            if info and info.get("gcode_files"):
                job.status = "sliced"
            else:
                job.status = "failed"
                job.notes.append("Bambu Studio meldete Erfolg, aber das 3MF enthält keinen G-Code.")
        else:
            job.status = "prepared"
    else:
        job.status = "failed"
        if result.returncode == 0:
            job.notes.append(f"Bambu Studio meldete Erfolg, aber {project.name} fehlt.")
    if result_json and result_json.get("error_string") and job.status != "sliced":
        job.notes.append(f"Bambu Studio: {result_json['error_string']}")
    write_reports(job)
    if job.status == "timeout":
        raise SlicerTimeoutError(f"Bambu Studio hat nach {timeout}s nicht geantwortet und wurde beendet.",
                                 hint="Mit --timeout ein höheres Limit setzen.",
                                 details={"job_dir": str(job.job_dir)})
    if job.status == "failed":
        raise SlicerError(f"Bambu Studio fehlgeschlagen: {job.exit['message']} ({job.exit['name']})",
                          hint=f"Details in {job.job_dir / job.files['log']}",
                          details={"job_dir": str(job.job_dir), "exit": job.exit})
    return job


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _fmt(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value) if len(value) < 6 else f"[{len(value)} Werte]"
    if value is None:
        return "–"
    text = str(value)
    return text if len(text) < 60 else text[:57] + "..."


def write_reports(job: Job) -> None:
    data = job.to_dict()
    _write_json(job.job_dir / job.files["report_json"], data)
    (job.job_dir / job.files["report_md"]).write_text(render_markdown(job), encoding="utf-8")


def render_markdown(job: Job) -> str:
    v = job.validation
    plan = job.plan
    lines = [f"# Bambu Butler Bericht: {job.slug}", "",
             f"**Status:** {STATUS_TEXT.get(job.status, job.status)}", "",
             "| Stufe | Ergebnis |", "|---|---|",
             "| Schema-gültig | ja |",
             f"| Mit Profilen kompatibel | {'ja' if v.compatible else 'nein'} |",
             f"| 3MF exportiert | {'ja' if job.status in ('prepared', 'sliced') else 'nein'} |",
             f"| Geslict | {'ja' if job.status == 'sliced' else 'nein'} |", "",
             "Es wurde **kein Druck gestartet**.", ""]
    if plan.request:
        lines += ["## Auftrag", "", f"> {plan.request}", ""]
    lines += ["## Profile", "", "| Rolle | Basisprofil | Verwendet als |", "|---|---|---|"]
    for key, info in job.profiles.items():
        lines.append(f"| {key} | {info['base']} | {info['name']} ({info['from']}) |")
    lines += ["", "## Änderungen gegenüber den Basisprofilen", ""]
    any_change = False
    for key, changes in job.changes.items():
        for c in changes:
            any_change = True
            lines.append(f"- **{key}.{c['key']}**: {_fmt(c['before'])} → {_fmt(c['after'])}"
                         + (f" _(aus {c['source']})_" if c.get("source") else ""))
    if not any_change:
        lines.append("Keine Änderungen.")
    if plan.rationale:
        lines += ["", "## Begründungen", ""]
        lines += [f"- **{r.setting}** = {_fmt(r.value)}: {r.reason}" for r in plan.rationale]
    if plan.assumptions:
        lines += ["", "## Annahmen", ""]
        lines += [f"- {a.text}" + (f" ({a.reason})" if a.reason else "") for a in plan.assumptions]
    if plan.open_questions:
        lines += ["", "## Offene Fragen", ""]
        lines += [f"- {'[blockierend] ' if q.blocking else ''}{q.question}" for q in plan.open_questions]
    if job.slice_summary:
        s = job.slice_summary
        lines += ["", "## Slicer-Ergebnis", "",
                  f"- Druckzeit: {slicer.format_duration(s.get('print_time_seconds'))}",
                  f"- Filament: {s['filament_g']} g" if s.get("filament_g") is not None else "- Filament: unbekannt",
                  f"- Quelle: {s['source']}"]
    if v.model_report:
        m = v.model_report
        lines += ["", "## Modell", "", f"- Datei: {m['path']}", f"- Objekte: {m['object_count']}"]
        if "size_after_transform_mm" in m:
            lines.append(f"- Größe nach Transformation: {' × '.join(str(x) for x in m['size_after_transform_mm'])} mm")
        if m.get("fit"):
            lines.append(f"- Passt in Druckraum: {'ja' if m['fit']['fits'] else 'nein'}")
    issues = [i for i in v.issues if i.level != "info"]
    if issues or job.notes:
        lines += ["", "## Hinweise", ""]
        lines += [f"- [{i.level}] {i.message}" for i in issues]
        lines += [f"- {n}" for n in job.notes]
    lines += ["", "## Aufruf", "", "```", json.dumps(job.argv, ensure_ascii=False, indent=1), "```", ""]
    if job.status in ("prepared", "sliced"):
        lines += ["## Nächster Schritt", "",
                  f"`bambu-butler open \"{job.job_dir / job.files['project']}\"`", ""]
    return "\n".join(lines)
