"""Error types with German user-facing messages and stable machine-readable codes."""

from __future__ import annotations


class ButlerError(Exception):
    """Base error. ``code`` is stable and meant for ``--json`` consumers."""

    code = "error"
    exit_code = 1

    def __init__(self, message: str, *, hint: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.details = details or {}

    def to_dict(self) -> dict:
        data = {"code": self.code, "message": self.message}
        if self.hint:
            data["hint"] = self.hint
        if self.details:
            data["details"] = self.details
        return data


class ConfigError(ButlerError):
    code = "config_error"


class StudioNotFoundError(ButlerError):
    code = "studio_not_found"
    exit_code = 3


class ProfileError(ButlerError):
    code = "profile_error"


class ProfileNotFoundError(ProfileError):
    code = "profile_not_found"


class InheritanceCycleError(ProfileError):
    code = "profile_inheritance_cycle"


class PlanError(ButlerError):
    code = "plan_invalid"
    exit_code = 2


class ModelFileError(ButlerError):
    code = "model_file_error"


class UnsafeArgumentError(ButlerError):
    code = "unsafe_argument"


class SlicerError(ButlerError):
    code = "slicer_failed"
    exit_code = 4


class SlicerTimeoutError(SlicerError):
    code = "slicer_timeout"


class NotSupportedError(ButlerError):
    code = "not_supported"
    exit_code = 5
