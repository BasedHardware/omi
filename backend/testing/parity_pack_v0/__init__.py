"""Local-only foundations for the Parity Pack v0 replay harness.

This package deliberately contains no production capture hook.  Capture wiring
is added by a later stage and must use :mod:`whitelist` before it writes a pack.
"""

from .schema import CassetteIdentity, RequestFingerprint
from .whitelist import CaptureWhitelist

__all__ = ("CassetteIdentity", "RequestFingerprint", "CaptureWhitelist")
