# Direct printer control

**Status in 0.0.1: not implemented.** `bambu-butler printer status` explains this;
`bambu-butler printer start` always fails with exit code 5. `prepare` and `slice` never touch the
printer.

## Why not yet

Print preparation is the focus of 0.0.1. Direct control has safety and interface questions that
need their own design:

- **No official public LAN API.** Bambu Lab printers are commonly controlled over the local network
  via MQTT over TLS (port 8883) and FTPS (port 990) using the printer's LAN access code. These
  interfaces are used by Bambu Studio / Bambu Handy and community projects, but they are not a
  documented, versioned public API.
- **Authorization changes.** Starting in 2025 Bambu Lab introduced an authorization layer for
  third-party control ("Bambu Connect"); depending on model and firmware, local third-party access
  may require LAN-only mode with Developer Mode enabled. Behaviour differs between printer series
  and firmware versions and must be verified per device before anything is implemented.
- **Physical safety.** Starting a print, changing temperatures or moving axes affects hardware.
  This must never happen as a side effect of slicing.

Verify the current state in Bambu Lab's official wiki and firmware release notes before building an
adapter; do not rely on this summary.

## Planned adapter interface

`src/bambu_butler/printer.py` defines the `PrinterAdapter` protocol:

```python
class PrinterAdapter(Protocol):
    def status(self) -> dict: ...
    def upload(self, project_path: str) -> None: ...
    def start_print(self, project_path: str, confirmation: PrintConfirmation) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def stop(self) -> None: ...
```

`PrintConfirmation` binds an explicit user approval to one project file (SHA-256) and one printer
serial. Requirements for a future adapter:

1. Opt-in per printer in `bambu-butler.json`; credentials (access code) read from the OS keychain or
   an environment variable, never printed or written to job folders.
2. TLS verification with the printer's certificate; no unencrypted fallbacks.
3. Capability detection per model/firmware; unsupported actions return `not_supported`.
4. `start_print` only with a `PrintConfirmation` created from an explicit user answer in the same
   session; the Claude Code skill must ask before every print.
5. Integration tests against a real printer are manual and documented.

Until then: open the sliced project in Bambu Studio (`bambu-butler open …`), check the preview and
start the print there.
