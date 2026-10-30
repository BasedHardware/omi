import json
from copy import deepcopy

import pytest

from scripts import validate_forward_audio_lifecycle as policy


@pytest.mark.parametrize('canonical', [True, False])
def test_forward_contract(canonical):
    filename = 'canonical-forward.json' if canonical else 'cache-forward.json'
    document = json.loads((policy.ROOT / filename).read_text())
    assert policy.validate(document, canonical=canonical) == []
    for field, bad in [
        ('newBucketOnly', False),
        ('versioning', {'enabled': True}),
        ('softDeletePolicy', {'retentionDurationSeconds': '604800'}),
        ('location', 'US'),
    ]:
        changed = {**document, field: bad}
        assert policy.validate(changed, canonical=canonical)
    for prefix in ['', 'chunks/', 'raw-mobile-batch/', 'playback/', 'canonical-packs-']:
        changed = deepcopy(document)
        changed['lifecycle']['rule'][0]['condition']['matchesPrefix'] = [prefix]
        assert policy.validate(changed, canonical=canonical)


def test_no_canonical_delete_or_unscoped_transition():
    document = json.loads((policy.ROOT / 'canonical-forward.json').read_text())
    document['lifecycle']['rule'][0]['action'] = {'type': 'Delete'}
    assert policy.validate(document, canonical=True)
    document = json.loads((policy.ROOT / 'canonical-forward.json').read_text())
    del document['lifecycle']['rule'][0]['condition']['matchesPrefix']
    assert policy.validate(document, canonical=True)
