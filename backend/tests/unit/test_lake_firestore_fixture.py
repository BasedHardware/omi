"""The lake query fake rejects unsupported semantics even under python -O."""

import os
import subprocess
import sys

import pytest
from google.cloud.firestore_v1.base_query import FieldFilter

from tests.unit.fixtures.lake_firestore import CandidateQuery, LakeFirestore


@pytest.mark.parametrize('field,op', [('key', '=='), ('key', '>'), ('bucket', '>=')])
def test_candidate_filter_rejects_unsupported_semantics(field, op):
    store = LakeFirestore()
    query = store.collection('lake_upload_candidates')
    with pytest.raises(NotImplementedError):
        query.where(filter=FieldFilter(field, op, 'a'))
    store.rows[('lake_upload_candidates', 'candidate')] = {'key': 'b'}
    with pytest.raises(NotImplementedError):
        list(CandidateQuery(store, ('lake_upload_candidates',), filters=(FieldFilter(field, op, 'a'),)).stream())


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
