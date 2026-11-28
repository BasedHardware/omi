"""Generated from config/feature-flags.yaml by scripts/render_shadow_expiry.py; do not edit.

A shadow row stops by itself: from the date here, config.refactor_modes.mode() reads a
``shadow`` binding as ``off`` (readout_by + 7 days; ruling: R-20261128-01, proposed).
"""

SHADOW_EXPIRES: dict[str, str] = {}
