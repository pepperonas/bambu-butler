# Feature status – Bambu Butler 0.0.1

Legend: ✅ implemented and tested · ✅✔ verified with a real Bambu Studio installation ·
🧪 implemented, tested only against a test double / sources · ⚠️ partial · ❌ not implemented

**Verified environment:** macOS (Apple Silicon), Bambu Studio 02.08.02.61, 2026-09-30.
`doctor --strict` succeeded and `slice examples/a1mini-pla-wandhalter.plan.json` produced a sliced
3MF (42 min 21 s, 11.26 g PLA). Bambu Studio accepted the resolved profile copies unchanged.

## Environment

| Feature | Status | Notes |
|---|---|---|
| Detect Bambu Studio executable (macOS/Windows/Linux defaults, PATH) | ✅✔ macOS | Overridable via CLI, env, config |
| Read version (macOS `Info.plist`, `--help` banner) | ✅✔ `Info.plist` | `BambuStudio-<version>` banner verified in sources |
| Detect available CLI options from `--help` | ✅✔ | Required: `--load-settings`, `--load-filaments`, `--export-3mf`, `--outputdir`, `--slice` |
| Locate resources and data directories | ✅✔ | No credentials are read or printed |

## Profiles

| Feature | Status | Notes |
|---|---|---|
| System profiles (`resources/profiles/<vendor>/…`, `data_dir/system/…`) | ✅✔ | Tested with real BBL profiles (v02.08) |
| User profiles (`data_dir/user/<id>/{machine,process,filament}`) | ✅✔ (11 filament profiles found) | |
| `inherits` + `include` resolution | ✅ | Mirrors `PresetBundle::load_vendor_configs_from_json` |
| Missing parents, cycles, broken JSON | ✅ | |
| Compatibility via `compatible_printers` | ✅ | |
| `compatible_printers_condition` | ⚠️ | Reported as "unknown", not evaluated |
| Project copies of profiles (`from: User`, `inherits: <system>`) | ✅✔ accepted by the CLI | Originals never modified |

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
| `prepare`: export unsliced 3MF via CLI | 🧪 not yet verified |
| `slice` with 3MF input (multi-colour, AMS) | 🧪 not yet verified |
| `slice`: slice all plates via CLI, parse `result.json` + `slice_info.config` | ✅✔ (STL input) |
| Bed type selection | ❌ |
| Per-object settings / modifiers / multiple plates in plan | ❌ |

## Bambu Studio GUI

| Feature | Status |
|---|---|
| Open project via OS (`open -a`, executable, `xdg-open`) | 🧪 command tested, launch not yet verified |
| macOS: check Automation/Accessibility permissions, app running, window titles | 🧪 |
| Automated clicks/keystrokes (slice button, dialogs) | ❌ deliberately; manual instructions instead |

## Printer

| Feature | Status |
|---|---|
| Send file, start/pause/stop print, temperatures, status | ❌ – see `printer-control.md` |
| Adapter interface with explicit confirmation object | ✅ (interface only) |
