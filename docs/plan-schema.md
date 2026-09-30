# Print plan schema v1

- Identifier: `"schema": "bambu-butler/print-plan"`, `"schema_version": "1"`
- JSON Schema: [`../schemas/print-plan.v1.schema.json`](../schemas/print-plan.v1.schema.json)
  (generated from `src/bambu_butler/plan.py` with `bambu-butler schema`)
- Unknown fields are rejected. Relative `model.path` is resolved against the plan file.

## Top level

| Field | Required | Meaning |
|---|---|---|
| `schema`, `schema_version` | yes (defaults) | Format identification |
| `$comment` | no | Free text, ignored |
| `request` | no | Original natural-language request |
| `model.path` | yes | `.stl` or `.3mf` |
| `printer.profile` | yes | Exact machine profile name |
| `printer.nozzle_diameter_mm` | no | Checked against the profile |
| `process.profile` | yes | Exact process profile name, must be compatible |
| `filaments[]` | yes (1–32) | `{profile, material?}`; order = filament slots 1..n |
| `settings` | no | Friendly settings, see below |
| `overrides.process/filament/machine` | no | Raw Bambu keys; must exist in the resolved base profile |
| `transform` | no | `rotate_x_deg`, `rotate_y_deg`, `rotate_z_deg`, `scale`, `auto_orient`, `arrange` |
| `output.directory`, `output.job_name` | no | Jobs root and job name |
| `assumptions[]` | no | `{text, reason?}` |
| `rationale[]` | no | `{setting, value, reason}` |
| `open_questions[]` | no | `{question, blocking}`; blocking questions stop `prepare`/`slice` |

## Settings

| Field | Bambu key |
|---|---|
| `quality.layer_height_mm` | `layer_height` |
| `quality.first_layer_height_mm` | `initial_layer_print_height` |
| `quality.seam` (`nearest`/`aligned`/`back`/`random`) | `seam_position` |
| `quality.ironing` (`none`/`top`/`topmost`/`solid`) | `ironing_type` |
| `strength.wall_loops` | `wall_loops` |
| `strength.top_layers` / `bottom_layers` | `top_shell_layers` / `bottom_shell_layers` |
| `strength.infill_density_percent` | `sparse_infill_density` |
| `strength.infill_pattern` | `sparse_infill_pattern` |
| `support.enabled` | `enable_support` |
| `support.style` (`normal_auto`/`tree_auto`/`normal_manual`/`tree_manual`) | `support_type` |
| `support.threshold_angle_deg` | `support_threshold_angle` |
| `support.build_plate_only` | `support_on_build_plate_only` |
| `adhesion.brim` (`auto`/`none`/`outer_only`/`inner_only`/`outer_and_inner`/`ears`) | `brim_type` |
| `adhesion.brim_width_mm` | `brim_width` |

All keys and enum values were checked against BambuStudio v02.08.04 `PrintConfig.cpp`.
Setting the same key through `settings` and `overrides.process` is an error.
`printable_area`, `printable_height` and `bed_exclude_area` cannot be overridden.

## Validation stages

1. **schema_valid** – pydantic validation succeeded.
2. **compatible_with_profiles** – no `error` issues from `validate` (profiles found and instantiable,
   `compatible_printers` match, material/nozzle match, known override keys, layer height within
   `min_layer_height`/`max_layer_height`, model fits after transform, 3MF slots exist).
3. **sliced** – only set by `slice` when Bambu Studio returned 0 and the exported 3MF contains G-code.

## Versioning

v1 only gains optional fields. Anything that changes meaning or removes fields becomes v2 and gets
its own schema file.
