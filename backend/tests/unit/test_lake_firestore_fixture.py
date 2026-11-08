"""The lake query fake rejects unsupported semantics even under python -O."""

import os
import subprocess
import sys

import pytest
from google.cloud.firestore_v1.base_query import FieldFilter

from tests.unit.fixtures.lake_firestore import CandidateQuery, LakeFirestore


@pytest.mark.parametrize('field,op', [('key', '=='), ('key', '>'), ('bucket', '>=')])
def test_candidate_filter_rejects_unsupported_semantics(field, op):
    query = LakeFirestore().collection('lake_upload_candidates')
    with pytest.raises(NotImplementedError):
        query.where(filter=FieldFilter(field, op, 'a'))
    with pytest.raises(NotImplementedError):
        CandidateQuery._matches('b', FieldFilter(field, op, 'a'))


def test_candidate_filter_rejects_unsupported_operator_with_optimization():
    code = """
from google.cloud.firestore_v1.base_query import FieldFilter
from tests.unit.fixtures.lake_firestore import LakeFirestore
query = LakeFirestore().collection('lake_upload_candidates')
try:
    query.where(filter=FieldFilter('key', '==', 'a'))
except NotImplementedError:
    pass
else:
    raise RuntimeError('Unsupported filter accepted under -O')
"""
    result = subprocess.run(
        [sys.executable, '-O', '-c', code], env=os.environ.copy(), capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
