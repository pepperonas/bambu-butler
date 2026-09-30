# CLAUDE.md

## Project

Bambu Butler: local CLI (`bambu-butler`, package `bambu_butler`) plus a Claude Code skill
(`.claude/skills/bambu-butler/`). Claude Code interprets print requests and writes JSON print
plans; the CLI validates them against real Bambu Studio profiles, writes job folders and calls
the Bambu Studio CLI. No LLM, no MCP, no network in the Python package.

## Using it (as the assistant)

For print requests follow `.claude/skills/bambu-butler/SKILL.md`. In short:
`doctor` → `inspect` → `profiles list/show` → `template` → edit plan → `validate` → `slice` → `open`.
Global options such as `--json` go before the subcommand. Never start a physical print.

## Development

```bash
uv sync
uv run pytest                 # full suite, no Bambu Studio required
uv run ruff check src tests
uv run bambu-butler schema -o schemas/print-plan.v1.schema.json   # after changing plan.py
```

Layout (`src/bambu_butler/`):

| Module | Responsibility |
|---|---|
| `cli.py` | Typer commands, Rich output, `--json` envelope, exit codes |
| `settings.py` / `platforms.py` | Path resolution: CLI > env > `bambu-butler.json` > OS defaults |
| `studio.py` | Executable detection, version, `--help` option parsing |
| `profiles.py` | Profile index, inheritance/`include` resolution, compatibility, CLI export |
| `plan.py` | Pydantic schema v1 (`bambu-butler/print-plan`) |
| `mapping.py` | Plan settings → verified Bambu Studio process keys |
| `validate.py` | Stage 2 checks (profiles, overrides, limits, model fit, 3MF slots) |
| `mesh.py` | STL/3MF reading and analysis (numpy) |
| `slicer.py` | Argument vector, CLI return codes, `result.json` / `slice_info.config` parsing |
| `jobs.py` | Job folder, execution, reports |
| `process.py` | Subprocess wrapper: argv only, timeouts kill the process group |
| `opener.py`, `gui_macos.py` | Open project; optional macOS checks (no clicks, no coordinates) |
| `printer.py` | Printer adapter interface only; raises `NotSupportedError` |

Docs: `README.md` (German, user-facing), `docs/cli.md`, `docs/plan-schema.md`, `docs/features.md`,
`docs/troubleshooting.md`, `docs/printer-control.md`, `docs/gui-macos.md`, `CHANGELOG.md`.

## Rules for changes

- Never add Bambu Studio CLI flags or profile keys without checking the Bambu Studio sources
  (`src/libslic3r/PrintConfig.cpp`, `src/BambuStudio.cpp`) or `--help` of an installed version.
  Record the version in `mapping.py` / `slicer.py`.
- External programs: argument lists only (`process.run`), never `shell=True` or joined strings.
  Paths in `--load-settings`/`--load-filaments` must not contain `;` or `"`.
- Plan schema v1 is stable: add optional fields only; breaking changes need `schema_version: "2"`.
  Regenerate `schemas/print-plan.v1.schema.json` (a test compares it).
- Do not present simulated results as real slices. Print time/material only from slicer output.
- Nothing may start a physical print implicitly. Printer control needs its own adapter with an
  explicit per-job confirmation.
- User-facing CLI text is German; code, identifiers and technical docs are English.
- Tests use synthetic profiles and a fake Bambu Studio executable (`tests/conftest.py`); keep it
  clearly a test double.

## Real integration test (needs Bambu Studio)

Last verified: macOS, Bambu Studio 02.08.02.61 (see `docs/features.md`). Update that file and
`CHANGELOG.md` when verifying new versions or platforms.

```bash
uv run bambu-butler doctor --strict
cd examples && uv run bambu-butler slice a1mini-pla-wandhalter.plan.json
```
