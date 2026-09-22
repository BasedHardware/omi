import tomllib
import math
from pathlib import Path
from typing import Any, Dict, Optional

class Config:
    """
    Represents the user configuration for the OMI CLI.

    Attributes
    ----------
    data : dict
        Parsed configuration data.
    load_error : Optional[Exception]
        Holds an exception if the configuration could not be loaded
        successfully.  When this is set, read‑only diagnostics are
        still available but write operations are blocked.
    """

    def __init__(self, data: Optional[Dict[str, Any]] = None, load_error: Optional[Exception] = None):
        self.data: Dict[str, Any] = data or {}
        self.load_error: Optional[Exception] = load_error

    @classmethod
    def load(cls, path: Path) -> "Config":
        """
        Load a configuration file from *path*.

        The function attempts to parse the TOML file and validate
        the `id_token_expires_at` field.  If the value is not a
        finite number or cannot be parsed, a ``ValueError`` is
        raised and captured in ``load_error`` so that the CLI can
        still provide read‑only diagnostics.

        Parameters
        ----------
        path : Path
            Path to the configuration file.

        Returns
        -------
        Config
            A configuration instance.  If loading failed, the
            ``load_error`` attribute will be set.
        """
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)

            # Validate the expiry value if present
            expiry = data.get("profiles", {}).get("default", {}).get("id_token_expires_at")
            if expiry is not None:
                try:
                    # ``math.isfinite`` will raise ``OverflowError`` for
                    # integers that are too large to convert to float.
                    if not math.isfinite(expiry):
                        raise ValueError("expiry value must be finite")
                except OverflowError:
                    # Treat an overflow as a malformed value – this
                    # mirrors the behaviour for non‑finite values and
                    # allows the CLI to recover gracefully.
                    raise ValueError("expiry value too large to process")

            return cls(data=data)

        except Exception as e:
            # Any exception during loading is captured so that the
            # CLI can still provide diagnostics.
            return cls(load_error=e)

    def save(self, path: Path) -> None:
        """
        Persist the configuration to *path*.

        The method refuses to overwrite a damaged configuration file
        (i.e. when ``load_error`` is set) to avoid accidental data
        loss.

        Parameters
        ----------
        path : Path
            Destination path for the configuration file.

        Raises
        ------
        RuntimeError
            If the configuration is damaged and cannot be safely
            written.
        """
        if self.load_error:
            raise RuntimeError("Cannot save damaged configuration")

        with path.open("wb") as f:
            tomllib.dump(self.data, f)
