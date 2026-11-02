"""Test rule: projection_followup coverage must keep one real-claim path.

David, 10-29 (simtests): the #23928 bug (a retry-deadline scope token created
in one Context and reset in another) was invisible to this suite because every
follow-up test stubbed ``projection_claim``. A stubbed claim can never test
the real claim's release semantics. This rule fails when the follow-up test
module no longer contains at least one non-skipped test that restores the REAL
``database.batch_pipeline_projection_claim.projection_claim`` against a
fakeredis instance.
"""

import ast
from pathlib import Path

FOLLOWUP_TESTS = Path(__file__).resolve().parent / 'test_batch_pipeline_projection_followup.py'
REAL_CLAIM_MODULE = 'batch_pipeline_projection_claim'


def test_followup_suite_keeps_a_real_claim_path_on_fakeredis():
    source = FOLLOWUP_TESTS.read_text()
    tree = ast.parse(source)
    qualifying = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith('test'):
            continue
        body = ast.get_source_segment(source, node) or ''
        if 'skip' in body:
            continue
        if REAL_CLAIM_MODULE in body and 'projection_claim' in body and 'fakeredis' in body:
            qualifying.append(node.name)
    assert qualifying, (
        'test_batch_pipeline_projection_followup.py has no test exercising the '
        'REAL projection_claim against fakeredis. The stubbed owner_claim '
        'fixture hides the claim release semantics (see #23928: the retry '
        'deadline scope crossed run_blocking Context boundaries and every '
        'release raised). Keep at least one real-claim path.'
    )
