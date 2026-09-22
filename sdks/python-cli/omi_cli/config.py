import math
import tomllib
from pathlib import Path
from typing import Any, Dict, Optional

# Existing imports and definitions omitted for brevity

class Config:
    """
    Represents the user configuration.  The `load_error` attribute is set
    when the configuration file cannot be parsed or contains invalid values.
    """
    def __init__(self, data: Optional[Dict[str, Any]] = None):
        self.data = data or {}
        self.load_error: Optional[str] = None

    # Existing methods omitted for brevity

def _validate_expiry(value: Any) -> None:
    """
    Validate the `id_token_expires_at` value.  The value is expected to be
    an integer that can be safely converted to a float for the `math.isfinite`
    check.  If the integer is too large for a float conversion, an
    `OverflowError` is raised by `float()`.  This function catches that
    exception and raises a `ValueError` with a clear message so that the
    caller can record the error in `Config.load_error` instead of
    propagating the exception.
    """
    try:
        # `math.isfinite` will raise `OverflowError` if the integer is too
        # large to convert to a float.  We catch that and treat it as an
        # invalid value.
        if not math.isfinite(float(value)):
            raise ValueError(f"expiry value {value!r} is not finite")
    except OverflowError:
        # Convert the overflow into a ValueError that can be handled by
        # the caller.  The message mirrors the one used for other
        # malformed values.
        raise ValueError(f"expiry value {value!r} is too large to parse")

def load(path: Path) -> Config:
    """
    Load a configuration file from `path`.  If the file contains an
    oversized integer for `id_token_expires_at`, the function will
    record a `load_error` instead of raising an exception.
    """
    cfg = Config()
    try:
        raw = path.read_bytes()
        parsed = tomllib.loads(raw)
    except Exception as exc:
        cfg.load_error = f"Failed to parse config: {exc}"
        return cfg

    # Validate each profile's expiry value
    for profile_name, profile in parsed.get("profiles", {}).items():
        expiry = profile.get("id_token_expires_at")
        if expiry is not None:
            try:
                _validate_expiry(expiry)
            except ValueError as exc:
                cfg.load_error = f"Profile '{profile_name}': {exc}"
                # Stop further processing; keep the config empty
                cfg.data = {}
                return cfg

    cfg.data = parsed
    return cfg
