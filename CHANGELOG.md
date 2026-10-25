# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Fixed
- Detecting Bambu Studio (`doctor` and every command that probes `--help`) no longer leaves a
  `result.json` in the current directory: Bambu Studio writes one even for `--help`, so the probe now
  runs in a temporary directory.
- Human-readable output no longer swallows text in square brackets. Profile names, paths, 3MF metadata
  and error messages were passed through Rich markup, so the project-copy suffix
  `[bambu-butler <job>]` disappeared from `inspect` and a name like `Foo [/x]` could break the output.

### Verified
- macOS, Bambu Studio 02.08.02.61: `prepare` exports an unsliced 3MF with the plan's settings in
  `Metadata/project_settings.config`; `slice` with that 3MF as input succeeds (42 min 6 s, 11.26 g PLA,
  read from `slice_info.config`).

### Documentation
- README reworked: status section with the verified real slice run, quick start, architecture diagram,
  configuration table, platform matrix, troubleshooting and badges.
- New `docs/cli.md` (full command reference) and `docs/troubleshooting.md`.
- `docs/features.md` updated with verification results.

## [0.0.1] – 2026-09-30

First usable version.

### Added
- CLI commands `init`, `doctor`, `profiles list`, `profiles show`, `inspect`, `template`, `validate`,
  `prepare`, `slice`, `open`, `schema`, `gui check`, `printer status`; `--json` output, dry runs, timeouts.
- Profile store for system and user profiles with `inherits`/`include` resolution, cycle and missing-parent
  detection, `compatible_printers` checks and project-specific profile copies.
- Print plan schema v1 (`bambu-butler/print-plan`) with mapping to Bambu Studio keys verified against the
  BambuStudio v02.08.04 sources.
- STL (binary/ASCII) and 3MF analysis: dimensions, units, objects, filament slots, project metadata,
  topology checks, fit to printable area.
- Job folders with resolved profiles, change list, command log, `result.json` and Markdown/JSON reports.
- Bambu Studio CLI integration (`--load-settings`, `--load-filaments`, `--slice 0`, `--export-3mf`,
  `--outputdir`), exit code table, parsing of `result.json` and `Metadata/slice_info.config`.
- Optional macOS GUI adapter (permissions, activation, window titles; no synthetic input).
- Printer adapter interface (not implemented) with explicit per-job confirmation.
- Claude Code skill `.claude/skills/bambu-butler/`, `CLAUDE.md`, examples and 77 tests.

### Verified
- macOS (Apple Silicon), Bambu Studio 02.08.02.61: `doctor --strict` and a real `slice` of
  `examples/a1mini-pla-wandhalter.plan.json` (42 min 21 s, 11.26 g PLA).
