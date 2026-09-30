# Feature status – Bambu Butler 0.0.1

Legend: ✅ implemented and tested · 🧪 implemented, tested only against a test double / sources ·
⚠️ partial · ❌ not implemented

## Environment

| Feature | Status | Notes |
|---|---|---|
| Detect Bambu Studio executable (macOS/Windows/Linux defaults, PATH) | ✅ | Overridable via CLI, env, config |
| Read version (macOS `Info.plist`, `--help` banner) | 🧪 | `BambuStudio-<version>` banner verified in sources |
| Detect available CLI options from `--help` | 🧪 | Required: `--load-settings`, `--load-filaments`, `--export-3mf`, `--outputdir`, `--slice` |
| Locate resources and data directories | ✅ | No credentials are read or printed |

## Profiles

| Feature | Status | Notes |
|---|---|---|
| System profiles (`resources/profiles/<vendor>/…`, `data_dir/system/…`) | ✅ | Tested with real BBL profiles (v02.08) |
| User profiles (`data_dir/user/<id>/{machine,process,filament}`) | ✅ | |
| `inherits` + `include` resolution | ✅ | Mirrors `PresetBundle::load_vendor_configs_from_json` |
| Missing parents, cycles, broken JSON | ✅ | |
| Compatibility via `compatible_printers` | ✅ | |
| `compatible_printers_condition` | ⚠️ | Reported as "unknown", not evaluated |
| Project copies of profiles (`from: User`, `inherits: <system>`) | ✅ | Originals never modified |

## Models

| Feature | Status | Notes |
|---|---|---|
| Binary/ASCII STL | ✅ | |
| 3MF (core + production extension, components, transforms, units) | ✅ | |
| Bambu 3MF metadata (object names, filament slots, project presets, sliced state) | ✅ | |
| Topology: open/non-manifold edges, degenerate triangles, flipped normals, volume | ✅ | Heuristic vertex welding at 1e-5 mm |
| Unit plausibility, fit to printable area/height after transform | ✅ | Rectangle check, no exclude areas |
| Load direction / optimal orientation / support need | ❌ | Not derivable reliably from a mesh |

## Plans and jobs

| Feature | Status |
|---|---|
| JSON schema v1, strict validation (unknown fields rejected) | ✅ |
| Friendly settings → verified Bambu keys, raw overrides with key check | ✅ |
| Layer height limits, nozzle, material checks | ✅ |
| Blocking open questions stop `prepare`/`slice` | ✅ |
| Job folder, changes, command log, Markdown/JSON report | ✅ |
| Dry run, timeouts (process group killed), `--json` | ✅ |
| `prepare`: export unsliced 3MF via CLI | 🧪 |
| `slice`: slice all plates via CLI, parse `result.json` + `slice_info.config` | 🧪 |
| Bed type selection | ❌ |
| Per-object settings / modifiers / multiple plates in plan | ❌ |

## Bambu Studio GUI

| Feature | Status |
|---|---|
| Open project via OS (`open -a`, executable, `xdg-open`) | ✅ (command built and tested; launching is OS-level) |
| macOS: check Automation/Accessibility permissions, app running, window titles | 🧪 |
| Automated clicks/keystrokes (slice button, dialogs) | ❌ deliberately; manual instructions instead |

## Printer

| Feature | Status |
|---|---|
| Send file, start/pause/stop print, temperatures, status | ❌ – see `printer-control.md` |
| Adapter interface with explicit confirmation object | ✅ (interface only) |
