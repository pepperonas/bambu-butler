"""Direct printer control - interface only, NOT implemented in 0.0.1.

Why not implemented (see docs/printer-control.md):

* Bambu Lab printers expose a LAN interface (MQTT over TLS on port 8883,
  FTPS for file upload) that is not officially documented as a public API.
* Bambu Lab introduced an authorization layer for third-party control in 2025
  ("Bambu Connect"); depending on model and firmware, local access may need
  LAN-only mode with Developer Mode. This must be verified per device.
* Starting a physical print must never happen implicitly. Any future adapter
  requires an explicit, per-job confirmation token.

``slice`` and ``prepare`` never import or call this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .errors import NotSupportedError


@dataclass(frozen=True)
class PrintConfirmation:
    """Explicit user approval for one project file. Required by ``start_print``."""

    project_sha256: str
    printer_serial: str
    confirmed_by_user: bool


class PrinterAdapter(Protocol):
    def status(self) -> dict: ...
    def upload(self, project_path: str) -> None: ...
    def start_print(self, project_path: str, confirmation: PrintConfirmation) -> None: ...
    def pause(self) -> None: ...
    def resume(self) -> None: ...
    def stop(self) -> None: ...


class NotImplementedAdapter:
    MESSAGE = ("Direkte Druckersteuerung ist in Bambu Butler 0.0.1 nicht implementiert. "
               "Projekt in Bambu Studio öffnen und den Druck dort manuell starten.")

    def _fail(self) -> None:
        raise NotSupportedError(self.MESSAGE, hint="Siehe docs/printer-control.md")

    def status(self) -> dict:
        self._fail()
        return {}

    def upload(self, project_path: str) -> None:
        self._fail()

    def start_print(self, project_path: str, confirmation: PrintConfirmation) -> None:
        self._fail()

    def pause(self) -> None:
        self._fail()

    def resume(self) -> None:
        self._fail()

    def stop(self) -> None:
        self._fail()


CAPABILITIES = {
    "send_file": "nicht implementiert",
    "start_print": "nicht implementiert (erfordert künftig ausdrückliche Freigabe)",
    "pause_resume_stop": "nicht implementiert",
    "set_temperature": "nicht implementiert",
    "status": "nicht implementiert",
}
