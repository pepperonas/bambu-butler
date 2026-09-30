---
name: bambu-butler
description: Prepare and slice 3D prints for Bambu Lab printers from a natural-language request. Use when the user wants to print, prepare, slice or tune settings for an .stl or .3mf file with Bambu Studio (e.g. "Bereite halter.stl für meinen A1 mini mit PLA vor"). Translates the request into a validated print plan and runs the local bambu-butler CLI. Never starts a physical print.
argument-hint: "[modell.stl|modell.3mf] [Druckwunsch]"
allowed-tools: Bash(bambu-butler *) Bash(uv run bambu-butler *) Read Write Edit
---

# Bambu Butler

You (Claude Code) interpret the user's print request. The `bambu-butler` CLI does the
verifiable work: it reads real Bambu Studio profiles, validates your plan, writes the job
folder, calls the Bambu Studio CLI and reports results. There is no LLM inside the CLI.

If `bambu-butler` is not on PATH, use `uv run bambu-butler` from the repository root.
Always add `--json` (a global option, placed **before** the subcommand) when you parse output.

## Hard rules

- Never start, send, pause or modify a physical print. `slice` and `prepare` never do.
  If the user asks to print, open the project and tell them to start it manually in
  Bambu Studio after checking the preview. A future printer adapter requires explicit
  user approval per job.
- Never invent profile names, Bambu Studio keys, CLI flags or printer features. Only use
  profile names returned by `profiles list` and keys shown by `profiles show` or listed in
  `reference.md`.
- Only report print time and filament usage when they come from `job.result` (real slicer
  output). If the status is not `sliced`, say so plainly.
- Keep the three stages apart when reporting: schema-valid plan, compatible with local
  profiles, actually sliced.
- Do not modify files in the Bambu Studio installation or data directory.

## Workflow

1. **Check the environment**
   `bambu-butler --json doctor` → note `can_slice`, `studio.version`, `missing`.
   If Bambu Studio is missing, continue with preparation but tell the user no real slice
   is possible.

2. **Inspect the model**
   `bambu-butler --json inspect <modell> --printer "<Druckerprofil>"`
   Use dimensions, fit, unit warnings, topology warnings, 3MF objects and filament slots.
   The mesh does not tell you load direction, best orientation or required supports; do not
   claim it does.

3. **Find profiles**
   `bambu-butler --json profiles list --type machine --query "A1 mini"`
   `bambu-butler --json profiles list --type process --printer "<Druckerprofil>"`
   `bambu-butler --json profiles list --type filament --printer "<Druckerprofil>" --query PLA`
   Prefer user profiles (`origin: user`) when the user has matching ones, otherwise the
   system profile for the right nozzle. Check values with
   `bambu-butler --json profiles show "<Name>" --keys layer_height,wall_loops,...`.

4. **Write the plan** (`plans/<name>.plan.json`, schema: `schemas/print-plan.v1.schema.json`).
   Start from `bambu-butler template <modell> --printer "<Druckerprofil>" -o plans/<name>.plan.json`
   and edit it. Put the original request into `request`.
   - Translate intent into `settings` (see `reference.md` for the mapping):
     strong → more `wall_loops`, more top/bottom layers, moderate infill (gyroid/cubic);
     clean visible surface → `seam: back` or `aligned`, finer layer height, optional ironing on
     flat tops; little support → keep orientation that avoids overhangs, `tree_auto`,
     `build_plate_only`, a sensible `threshold_angle_deg`.
   - Use `overrides.process|filament|machine` only for keys that exist in the base profile.
   - Every non-default choice gets a `rationale` entry; every guess goes to `assumptions`.
   - Unknown but important facts go to `open_questions`. Mark `blocking: true` only when the
     result would be wrong without the answer.

5. **Ask only when decisive information is missing**, e.g. material unknown and no default
   filament is plausible, or the load direction decides the orientation. Otherwise decide,
   document the assumption and proceed; preparation is reversible.

6. **Validate**
   `bambu-butler --json validate plans/<name>.plan.json`
   Fix every `error` issue (wrong profile names, incompatible profiles, unknown keys, model
   does not fit, layer height outside printer limits) and re-validate.

7. **Prepare and slice**
   Optional preview: `bambu-butler --json slice plans/<name>.plan.json --dry-run`
   Then: `bambu-butler --json slice plans/<name>.plan.json`
   - Exit 3 / `studio_not_found`: Bambu Studio missing; the job folder still contains the
     resolved profiles, change list and exact command.
   - Exit 4 / `slicer_failed`: read `error.details.exit` and `cli.log` in the job folder,
     adjust the plan (e.g. brim, supports, orientation) and try again once or twice.
   - `slicer_timeout`: retry with `--timeout 1200` if the model is large.

8. **Report and open**
   Summarise from `job.status`, `job.changes`, `job.result`, assumptions and warnings, in
   German. Then open the result:
   `bambu-butler open "<job_dir>/<name>.3mf"`
   Tell the user to check the preview in Bambu Studio and to start the print manually.

## Example exchange

User: „Bereite halter.stl für meinen Bambu Lab A1 mini mit PLA vor. Die Halterung soll stabil
sein, eine saubere sichtbare Oberfläche haben und möglichst wenig Support benötigen.“

You: run doctor → inspect → profiles list → template → edit plan (e.g. `wall_loops: 4`,
`top_layers: 5`, `infill_density_percent: 25`, `infill_pattern: gyroid`, `seam: back`,
`support: {enabled: true, style: tree_auto, build_plate_only: true}` only if overhangs are
likely) → validate → slice → summarise → open.

See `reference.md` for the plan field → Bambu Studio key mapping and the CLI exit codes.
