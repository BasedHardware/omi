"""Prod-shaped synthetic load for staging (plan F §3.4, swarm lane 4).

- ``profile.json``: prod arrival histograms (aggregates only, k>=20, no uids),
  refreshed by ``refresh_profile.py`` from ro-prod Prometheus.
- ``population.py``: deterministic synthetic population (pseudo-owners, time
  shifts, silence, upload-order variation including reverse uploads).
- ``mirror_codec.py``: the staging-mirror envelope shared by
  ``scripts/staging/mirror_owner_recordings.py`` and ``scripts/staging/replay.py``.

Nothing here performs IO at import time.
"""
