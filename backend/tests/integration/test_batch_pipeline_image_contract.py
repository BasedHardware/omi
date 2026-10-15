"""Whole-source packaging integration; no Docker daemon or deployment required."""

from pathlib import Path
import pytest

pytestmark = pytest.mark.integration
CHART = Path(__file__).resolve().parents[2] / 'charts' / 'batch-pipeline-worker'


def test_joint_image_contains_runtime_first_party_import_closure():
    # This image has no deployment workflow by design. Exercise the existing
    # closure guard directly until a lead-authorized publication workflow exists.
    from dataclasses import replace
    from scripts.runtime_image_contracts import load_contracts, source_closure_errors

    base = next(image for image in load_contracts() if image.name == 'backend')
    contract = replace(
        base,
        name='batch-pipeline-worker',
        dockerfile=CHART.parents[1] / 'diarizer' / 'Dockerfile.batch-pipeline',
        deployment_workflows=(),
        entrypoints=('diarizer.batch_pipeline_runtime',),
    )
    assert source_closure_errors(contract) == []
