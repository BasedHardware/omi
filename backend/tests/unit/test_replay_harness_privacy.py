"""Lightweight deterministic corpus/wire checks; real readers belong in integration."""

import json
from pathlib import Path

import pytest

from testing.replay_harness.gen_privacy_timeline import FAULTS, KINDS, generate, write_case
from testing.replay_harness.manifest import load_case
from testing.replay_harness.stages.privacy_scenarios import validate_rows

FIXTURE = Path(__file__).resolve().parents[2] / 'testing/replay_harness/fixtures/privacy-transitions-smoke'


def test_smoke_is_byte_reproducible_and_covers_kinds_and_family_faults(tmp_path):
    write_case(tmp_path / FIXTURE.name, transitions=120)
    for name in ('corpus.json', 'manifest.json'):
        assert (tmp_path / FIXTURE.name / name).read_bytes() == (FIXTURE / name).read_bytes()
    case = load_case(FIXTURE)
    rows = validate_rows(case.corpus)
    assert case.manifest.schema_version == 1
    assert {(r['family'], r['kind']) for r in rows} == {(f, k) for f in KINDS for k in KINDS[f]}
    assert {(r['family'], r['fault']) for r in rows} == {(f, fault) for f in KINDS for fault in FAULTS}


def test_full_corpus_is_stable_bounded_and_has_no_identity_fields():
    first, second = generate(), generate()
    assert json.dumps(first) == json.dumps(second)
    rows = validate_rows(first)
    assert len(rows) == 1000
    assert generate(seed=7) != first
    assert all(set(r) == {'family', 'kind', 'fault'} for r in rows)


@pytest.mark.parametrize(
    'seed',
    [
        None,
        {},
        {'transitions': []},
        {'transitions': [{}]},
        {'transitions': [{'family': 'secret-uid', 'kind': 'create', 'fault': 'none'}]},
    ],
)
def test_bad_timeline_rejected_before_infrastructure(seed):
    with pytest.raises(ValueError):
        validate_rows({'privacy_cache': seed})


@pytest.mark.parametrize(
    'kwargs',
    [
        dict(transitions=0),
        dict(transitions=10001),
        dict(transitions=True),
        dict(mix={'unknown': 1}),
        dict(mix={'tombstone': 0}),
        dict(faults=['unknown']),
    ],
)
def test_generator_rejects_unbounded_or_unknown_controls(kwargs):
    with pytest.raises(ValueError):
        generate(**kwargs)
