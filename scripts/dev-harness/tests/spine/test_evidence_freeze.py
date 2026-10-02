"""V8 active contract: validation changes require v2, not a new baseline."""
import copy
import hashlib
import json
from pathlib import Path

ANNOTATIONS = {'title', 'description', '$comment', 'examples'}


def validation_shape(value):
    if isinstance(value, dict):
        return {key: ({name: validation_shape(child) for name, child in item.items()}
                      if key in ('properties', '$defs', 'patternProperties', 'dependentSchemas')
                      else validation_shape(item))
                for key, item in value.items() if key not in ANNOTATIONS}
    if isinstance(value, list):
        return [validation_shape(item) for item in value]
    return value


def digest(schema):
    return hashlib.sha256(json.dumps(validation_shape(schema), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def schema():
    return json.loads((Path(__file__).resolve().parents[4] / 'contracts/session/session-evidence-v1.schema.json').read_text())


FROZEN_SHA256 = '0470597d494ac35c3f9f78123d497bb3e86b31b2074139599c8ce90b8d297d05'


def test_v1_validation_structure_is_frozen():
    assert digest(schema()) == FROZEN_SHA256, 'v1 validation changed: introduce v2; never update this digest'


def test_annotation_only_edits_do_not_change_validation():
    candidate = schema()
    candidate['description'] = 'Clarified documentation'
    candidate['properties']['live']['title'] = 'Live operation'
    assert digest(candidate) == FROZEN_SHA256


def test_freeze_detects_optional_addition_and_nested_widening():
    original = schema()
    mutations = [
        lambda s: s['properties'].update({'optional_new_field': {'type': 'string'}}),
        lambda s: s['properties'].update({'description': {'type': 'string'}}),
        lambda s: s['required'].append('artifact'),
        lambda s: s['properties']['target']['properties']['profile']['enum'].append('mobile_beta'),
        lambda s: s['$defs']['hex40'].update({'pattern': '.*'}),
        lambda s: s['properties']['live'].update({'additionalProperties': True}),
        lambda s: s['properties']['source']['properties'].pop('dirty_digest'),
    ]
    for mutate in mutations:
        candidate = copy.deepcopy(original)
        mutate(candidate)
        assert digest(candidate) != FROZEN_SHA256
