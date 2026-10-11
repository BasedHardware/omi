"""Offline conversation-summary lab.

Transcription-in → pipeline → summary-out, comparable across variants.
Production modules are not imported unless a live seam is opted into.
"""

from __future__ import annotations

from testing.summary_lab.compare import compare_runs, compare_variants
from testing.summary_lab.fixtures import Fixture, load_synthetic_fixtures
from testing.summary_lab.judge import JudgeReport, score_note
from testing.summary_lab.pricing import estimate_usd
from testing.summary_lab.runner import LabRun, run_matrix
from testing.summary_lab.variants import VARIANTS, Variant

__all__ = [
    'Fixture',
    'JudgeReport',
    'LabRun',
    'VARIANTS',
    'Variant',
    'compare_runs',
    'compare_variants',
    'estimate_usd',
    'load_synthetic_fixtures',
    'run_matrix',
    'score_note',
]
