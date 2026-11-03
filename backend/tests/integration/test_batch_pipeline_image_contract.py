"""Whole-source packaging integration; no Docker daemon or deployment required."""

import pytest

pytestmark = pytest.mark.integration


def test_joint_image_contains_runtime_first_party_import_closure():
    from scripts.runtime_image_contracts import load_contracts, source_closure_errors

    contract = next(image for image in load_contracts() if image.name == 'batch-pipeline-worker')
    assert source_closure_errors(contract) == []
