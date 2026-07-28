"""Typed failures raised by the projection steps and caught at the composition boundary."""

from __future__ import annotations


class NoProjectionSubject(Exception):
    """There is nothing to project from.

    The bottom rung of the evidence ladder. Raised rather than papered over: a projection
    with no evidence behind it is the evidence-free artifact this feature exists to replace,
    so an empty corpus must surface as a refusal the caller reports.
    """
