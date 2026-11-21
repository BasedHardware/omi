"""Pipeline-lab cache keys (DESIGN L12): what invalidates and what does not. Synthetic only."""

import pytest

from testing.pipeline_lab import keys

TREE = 'a' * 40
BASE = dict(
    backend_tree=TREE,
    inputs={'corpus_day': '1' * 64, 'stage:transcribe': '2' * 64},
    overlay={'env': {'NOTES_MODE': 'serve', 'X': '1'}, 'pins': {'notes_serving_for': 'all'}},
    model_config={'notes': {'model': 'm-1', 'provider': 'p'}},
)


def key(**changes):
    params = {**BASE, **changes}
    return keys.stage_key('notes', **params)


def test_same_inputs_same_key_and_hex():
    assert key() == key()
    assert len(key()) == 64 and int(key(), 16) >= 0


@pytest.mark.parametrize(
    'change',
    [
        {'backend_tree': 'b' * 40},
        {'inputs': {**BASE['inputs'], 'stage:transcribe': '3' * 64}},
        {'inputs': {**BASE['inputs'], 'stage:speakers': '4' * 64}},
        {'overlay': {**BASE['overlay'], 'env': {'NOTES_MODE': 'shadow', 'X': '1'}}},
        {'overlay': {**BASE['overlay'], 'pins': {'notes_serving_for': 'none'}}},
        {'model_config': {'notes': {'model': 'm-2', 'provider': 'p'}}},
        {'schema_version': 2},
    ],
    ids=['tree', 'input-changed', 'input-added', 'overlay-env', 'overlay-pin', 'model', 'schema'],
)
def test_each_component_invalidates(change):
    assert key(**change) != key()


def test_stage_name_invalidates():
    assert keys.stage_key('memories', **BASE) != key()
    assert keys.stage_key('notes:conv-1', **BASE) != keys.stage_key('notes:conv-2', **BASE)


def test_ordering_does_not_invalidate():
    reordered_inputs = dict(reversed(list(BASE['inputs'].items())))
    reordered_overlay = {'pins': BASE['overlay']['pins'], 'env': {'X': '1', 'NOTES_MODE': 'serve'}}
    assert key(inputs=reordered_inputs, overlay=reordered_overlay) == key()


def test_commit_sha_and_run_identity_are_not_inputs():
    # Two commits with an identical backend/ share a tree hash, hence a key: the
    # key takes no commit, run id, path or clock argument at all.
    material = keys.CacheKey(stage='notes', **BASE).material()
    assert set(material) == {
        'key_version',
        'stage',
        'schema_version',
        'inputs',
        'backend_tree',
        'overlay',
        'model_config',
    }


def test_unknown_stage_and_missing_tree_are_refused():
    with pytest.raises(ValueError):
        keys.stage_key('nope', **BASE)
    with pytest.raises(ValueError):
        keys.stage_key('notes', **{**BASE, 'backend_tree': ''})


def test_hash_json_is_canonical():
    assert keys.hash_json({'b': 1, 'a': [1, 2]}) == keys.hash_json({'a': [1, 2], 'b': 1})
    assert keys.hash_json({'a': 'é'}) != keys.hash_json({'a': 'e'})


def test_hash_file(tmp_path):
    path = tmp_path / 'x'
    path.write_bytes(b'abc')
    assert keys.hash_file(path) == keys.sha256_hex(b'abc')
