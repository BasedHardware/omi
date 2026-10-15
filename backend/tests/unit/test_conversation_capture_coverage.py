"""Public coverage projection never exposes the internal source-position receipt."""

from datetime import datetime, timezone
import pytest
from models.conversation import Conversation


@pytest.mark.parametrize('coverage', ['incomplete', 'mapped', 'unknown', None])
def test_capture_coverage_projects_existing_receipt_only(coverage):
    row = dict(id='c', created_at=datetime.now(timezone.utc), started_at=None, finished_at=None, structured={})
    if coverage is not None:
        row['capture_evidence'] = dict(
            capability='source_position', coverage=coverage, capture_root='private', runs=[{'start': 1}]
        )
    conversation = Conversation(**row)
    assert conversation.model_dump(mode='json')['capture_coverage'] == coverage
    assert 'capture_evidence' not in conversation.model_dump(mode='json')
    assert 'capture_evidence' not in conversation.model_dump()


def test_legacy_and_public_projection_roundtrip():
    row = dict(id='c', created_at=datetime.now(timezone.utc), started_at=None, finished_at=None, structured={})
    assert Conversation(**row).capture_coverage is None
    public = Conversation(**row, capture_coverage='incomplete').model_dump(mode='json')
    assert Conversation(**public).capture_coverage == 'incomplete'
