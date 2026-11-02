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


def test_source_gate_keeps_forward_archive_separate_from_existing_prod_stock(tmp_path, monkeypatch):
    for filename in ('canonical-forward.json', 'cache-forward.json', 'prod.json'):
        (tmp_path / filename).write_text((policy.ROOT / filename).read_text())
    monkeypatch.setattr(policy, 'ROOT', tmp_path)
    assert policy.main() == 0  # The new-empty-bucket Archive proposal still passes.
    prod = json.loads((tmp_path / 'prod.json').read_text())
    prod['lifecycle']['rule'].append(
        {
            'action': {'type': 'SetStorageClass', 'storageClass': 'ARCHIVE'},
            'condition': {
                'age': 90,
                'matchesPrefix': ['chunks/'],
                'matchesStorageClass': ['COLDLINE'],
                'matchesSuffix': ['.batch.enc', '.batch.bin'],
            },
        }
    )
    (tmp_path / 'prod.json').write_text(json.dumps(prod))
    assert policy.main() == 1
