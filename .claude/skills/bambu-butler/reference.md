# Bambu Butler reference

Verified against BambuStudio v02.08.04 sources (`src/libslic3r/PrintConfig.cpp`,
`src/libslic3r/Utils.hpp`, `src/BambuStudio.cpp`).

## Plan settings → Bambu Studio process keys

| Plan field | Bambu key | Values |
|---|---|---|
| `settings.quality.layer_height_mm` | `layer_height` | mm, within printer `min_layer_height`..`max_layer_height` |
| `settings.quality.first_layer_height_mm` | `initial_layer_print_height` | mm |
| `settings.quality.seam` | `seam_position` | `nearest`, `aligned`, `back`, `random` |
| `settings.quality.ironing` | `ironing_type` | `none`→`no ironing`, `top`, `topmost`, `solid` |
| `settings.strength.wall_loops` | `wall_loops` | int |
| `settings.strength.top_layers` | `top_shell_layers` | int |
| `settings.strength.bottom_layers` | `bottom_shell_layers` | int |
| `settings.strength.infill_density_percent` | `sparse_infill_density` | 0–100 → `"25%"` |
| `settings.strength.infill_pattern` | `sparse_infill_pattern` | `grid`, `gyroid`, `cubic`, `adaptivecubic`, `lightning`, `honeycomb`, `3dhoneycomb`, `triangles`, `tri-hexagon`, `line`, `zig-zag`, `concentric`, `crosshatch`, … |
| `settings.support.enabled` | `enable_support` | bool → `"1"`/`"0"` |
| `settings.support.style` | `support_type` | `normal_auto`→`normal(auto)`, `tree_auto`→`tree(auto)`, `normal_manual`, `tree_manual` |
| `settings.support.threshold_angle_deg` | `support_threshold_angle` | 1–90 |
| `settings.support.build_plate_only` | `support_on_build_plate_only` | bool |
| `settings.adhesion.brim` | `brim_type` | `auto`→`auto_brim`, `none`→`no_brim`, `outer_only`, `inner_only`, `outer_and_inner`, `ears`→`brim_ears` |
| `settings.adhesion.brim_width_mm` | `brim_width` | mm |

Other keys: use `overrides.process` / `overrides.filament` / `overrides.machine` with the exact
key name as shown by `bambu-butler profiles show "<profile>"`. Vector values (per extruder) are
expanded automatically. `printable_area`, `printable_height`, `bed_exclude_area` cannot be
overridden (the Bambu CLI rejects it).

Examples of existing filament keys: `nozzle_temperature`, `nozzle_temperature_initial_layer`,
`hot_plate_temp`, `textured_plate_temp`, `fan_max_speed`, `filament_max_volumetric_speed`.
Check they exist in the chosen profile before using them.

## Transform → Bambu CLI

| Plan | CLI |
|---|---|
| `rotate_x_deg` / `rotate_y_deg` / `rotate_z_deg` | `--rotate-x` / `--rotate-y` / `--rotate` (applied in this order), plus `--ensure-on-bed` |
| `scale` | `--scale` |
| `auto_orient` | `--orient 1` (else `--orient 0`) |
| `arrange` | `--arrange 1` (else `--arrange 0`) |

## Job statuses

`dry_run`, `prepared_without_studio`, `prepared` (3MF exported, not sliced), `sliced`,
`failed`, `timeout`.

## CLI exit codes of bambu-butler

0 ok · 1 general error · 2 plan invalid/incompatible · 3 Bambu Studio missing ·
4 slicer failed/timeout · 5 not supported (printer control)

## Common Bambu Studio CLI return codes (`job.exit.name`)

`CLI_CONFIG_FILE_ERROR` (-5) profile JSON rejected · `CLI_PROCESS_NOT_COMPATIBLE` (-17) ·
`CLI_OBJECTS_PARTLY_INSIDE` (-52) move/scale model · `CLI_SLICING_ERROR` (-100) ·
`CLI_GCODE_PATH_OUTSIDE` (-104) brim/support outside bed · `CLI_FILAMENT_NOT_MATCH_BED_TYPE` (-61).
Full table: `src/bambu_butler/slicer.py`.
