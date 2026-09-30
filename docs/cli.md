# CLI reference

```text
bambu-butler [GLOBAL OPTIONS] COMMAND [ARGS] [OPTIONS]
```

Global options must come **before** the command.

| Option | Meaning |
|---|---|
| `--json` | Machine-readable output. Success: `{"ok": true, …}`. Error: `{"ok": false, "error": {"code", "message", "hint"?, "details"?}}` |
| `--studio PATH` | Bambu Studio executable |
| `--resources PATH` | Bambu Studio resources directory (contains `profiles/`) |
| `--data-dir PATH` | Bambu Studio data directory (contains `user/`, `system/`) |
| `--jobs-dir PATH` | Root directory for job folders |
| `--config FILE` | Explicit `bambu-butler.json` |
| `--version` | Print version |

## Exit codes

| Code | Meaning | Typical `error.code` |
|---|---|---|
| 0 | Success | – |
| 1 | General error | `profile_not_found`, `profile_error`, `model_file_error`, `config_error`, `error` |
| 2 | Plan invalid or incompatible | `plan_invalid` (schema), `validate` with errors |
| 3 | Bambu Studio missing / CLI unusable | `studio_not_found` (also `doctor --strict`) |
| 4 | Slicer failed or timed out | `slicer_failed`, `slicer_timeout` |
| 5 | Not supported | `not_supported` (printer control) |

## `init [DIRECTORY] [--force]`

Creates `bambu-butler.json` (with auto-detected paths), `jobs/` and `plans/`. Existing configuration is kept unless `--force`.

## `doctor [--strict]`

Detects executable, version (`Info.plist` on macOS, otherwise the `BambuStudio-<version>` banner of `--help`),
CLI options, resource and data directories, profile counts and missing dependencies.
`--strict` exits with 3 when slicing is not possible.

JSON fields: `studio` (`executable`, `version`, `version_source`, `cli_usable`, `required_options`, `optional_options`,
`problems`), `settings` (resolved paths and their `sources`: `cli`, `env:…`, `config`, `auto`, `default`),
`profile_counts`, `printers`, `missing`, `can_prepare_profiles`, `can_slice`.

## `profiles list`

| Option | Meaning |
|---|---|
| `-t, --type` | `machine`, `process`, `filament` |
| `-p, --printer NAME` | Only profiles compatible with this machine profile (`compatible` = `ja` / `unklar`) |
| `-q, --query TEXT` | Case-insensitive substring filter on the name |
| `--vendor NAME` | Vendor folder of system profiles, e.g. `BBL` |
| `--all` | Include base/template profiles (`instantiation: false`) |

## `profiles show NAME`

| Option | Meaning |
|---|---|
| `-t, --type` | Disambiguate by type |
| `--raw` | The file as stored, without inheritance |
| `-k, --keys a,b,c` | Only these keys |

JSON: `profile`, `chain` (base → profile), `system_name`, `filament_id`, `warnings`, `values`.

## `inspect MODEL [-p PRINTER]`

STL (binary/ASCII) or 3MF. Reports bounding box, unit (3MF `unit` attribute; STL has none), objects with
triangle counts, sizes and filament slots, Bambu project metadata, topology (`open_edges`, `non_manifold_edges`,
`degenerate_triangles`, `inconsistently_oriented_edges`, `signed_volume_mm3`) and, with `-p`, the fit check.

## `template MODEL -p PRINTER [--process P] [-f FILAMENT …] [-o FILE]`

Writes a schema-valid plan using the printer's `default_print_profile` and `default_filament_profile`
unless overridden. The model path is stored relative to the plan file.

## `validate PLAN`

Stage 1 (schema) and stage 2 (compatibility). Exit 2 if incompatible. JSON: `validation.stages`,
`validation.issues[]` (`level`, `code`, `message`), `validation.overrides`, `validation.model`.

Issue codes: `profile_not_found`, `profile_not_instantiable`, `incompatible_profile`, `compatibility_unknown`,
`material_mismatch`, `nozzle_mismatch`, `unknown_key`, `override_conflict`, `layer_height_out_of_range`,
`model_too_large`, `model_file_error`, `filament_slot_missing`, `filament_count_changes`, `multi_filament`,
`blocking_question`, `model_warning`, `already_sliced`, `support_disabled`.

## `prepare PLAN` / `slice PLAN`

| Option | Meaning |
|---|---|
| `--dry-run` | Show the planned changes and argument list; write and run nothing |
| `--timeout S` | Kill Bambu Studio (whole process group) after S seconds |
| `--allow-open-questions` | Proceed despite blocking open questions |

`prepare` exports `<job>.prepared.3mf` without `--slice`; `slice` adds `--slice 0` and exports `<job>.3mf`.
Without a usable Bambu Studio, `prepare` still writes the job folder (status `prepared_without_studio`, exit 0)
while `slice` writes it and exits 3.

JSON `job` fields: `status` (`dry_run`, `prepared_without_studio`, `prepared`, `sliced`, `failed`, `timeout`),
`stages`, `job_dir`, `files`, `profiles`, `changes`, `command`, `run`, `exit` (`code`, `name`, `message`),
`result` (`print_time_seconds`, `filament_g`, `source`, `plates`), `issues`, `notes`, `print_started` (always `false`).

Generated Bambu Studio call (argument list, never a shell string):

```text
BambuStudio [--rotate-x X] [--rotate-y Y] [--rotate Z] [--scale F] [--ensure-on-bed]
            --orient 0|1 --arrange 0|1
            --load-settings "<job>/profiles/machine.json;<job>/profiles/process.json"
            --load-filaments "<job>/profiles/filament_1.json[;…]"
            [--slice 0] --export-3mf <name>.3mf --outputdir <job> --debug 2
            <job>/input/<model>
```

## `open PROJECT [--dry-run] [--check-gui]`

macOS: `open -a <BambuStudio.app> <file>`; Windows: executable with the file; Linux: executable or `xdg-open`.
`--check-gui` (macOS) waits 3 s and reports permissions and window titles.

## `schema [-o FILE]`, `gui check [--expect NAME]`, `printer status`, `printer start`

`printer start` always fails with exit 5 – direct printer control is not implemented.
