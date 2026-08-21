"""Tests for the runtime-env parity ratchet (ADR-0061).

The guard exists because our deployment environment was assembled by discovery while upstream's is
declared in one file and enforced at deploy time. Two measured consequences on this stack:
``MEMORY_ENABLED`` unset makes every memory write answer 503, and ``MEMORY_V3_CURSOR_SECRET`` unset
breaks cursor pagination past the first page. Both are variables nobody looked at, not code bugs.

Driven through the pure ``check``/``upstream_declared``/``ours_declared`` functions over strings, so
these tests are hermetic.
"""

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / '.github' / 'scripts' / 'check_oss_runtime_env_parity.py'
if not _SCRIPT.exists():
    # Repo-root guard script — absent when only backend/ is mounted (the offline test image).
    # CI checks out the full repo, so the guard still runs there.
    pytest.skip(f'guard script not present at {_SCRIPT}', allow_module_level=True)
_SPEC = importlib.util.spec_from_file_location('check_oss_runtime_env_parity', _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


UPSTREAM = """
services:
  backend:
    prod:
      env:
        MEMORY_ENABLED:
          category: memory_rollout
          value: 'on'
        MEMORY_V3_CURSOR_SECRET:
          secret: MEMORY_V3_CURSOR_SECRET
        STORAGE_BACKEND:
          value: firestore
        # COMMENTED_OUT_SWITCH: a comment is not a declaration
    flags:
      --set-env-vars: SOME_INLINE_VAR=1,ANOTHER_INLINE_VAR=2
      --remove-env-vars: RETIRED_VAR
"""


def test_reads_every_declaration_form_upstream_uses():
    assert _MODULE.upstream_declared(UPSTREAM) == {
        'MEMORY_ENABLED',
        'MEMORY_V3_CURSOR_SECRET',
        'STORAGE_BACKEND',
        'SOME_INLINE_VAR',
        'ANOTHER_INLINE_VAR',
        'RETIRED_VAR',
    }
    assert 'COMMENTED_OUT_SWITCH' not in _MODULE.upstream_declared(UPSTREAM)


def test_an_env_file_example_declares_its_variables():
    text = """
# STORAGE_BACKEND selects the document store
STORAGE_BACKEND=mongo
MONGO_URI=mongodb://mongo:27017
# COMMENTED=not-a-declaration
"""
    assert _MODULE.ours_declared({'deploy/onprem/backend.env.base.example': text}) == {
        'STORAGE_BACKEND',
        'MONGO_URI',
    }


def test_an_interpolation_is_a_use_not_a_declaration():
    """Believing we declare something we do not is the one error direction that hides a gap."""
    text = """
services:
  backend:
    image: omi-oss-backend:${OMI_OSS_RELEASE:?}
    environment:
      STORAGE_BACKEND: mongo
"""
    assert _MODULE.ours_declared({'deploy/onprem/compose.base.yaml': text}) == {'STORAGE_BACKEND'}


def test_another_services_environment_does_not_count_as_ours():
    """Mongo's own env must not make a backend variable look declared."""
    text = """
services:
  backend:
    environment:
      STORAGE_BACKEND: mongo
  mongo:
    environment:
      MEMORY_ENABLED: on
      MONGO_INITDB_ROOT_USERNAME: root
  keycloak:
    environment:
      KC_DB: postgres
volumes:
  mongo_data:
"""
    declared = _MODULE.ours_declared({'deploy/onprem/compose.selfhost.yaml': text})
    assert declared == {'STORAGE_BACKEND'}
    assert 'MEMORY_ENABLED' not in declared, 'mongo declaring it is not us declaring it for the backend'


def test_a_helm_template_counts_every_key():
    """A backend ConfigMap/Secret holds nothing but backend env, so no service filter applies."""
    text = """
apiVersion: v1
kind: ConfigMap
data:
  STORAGE_BACKEND: mongo
  S3_ENDPOINT: http://rustfs:9000
"""
    assert _MODULE.ours_declared({'deploy/onprem/helm/omi-oss/templates/backend-configmap.yaml': text}) == {
        'STORAGE_BACKEND',
        'S3_ENDPOINT',
    }


def test_a_variable_we_neither_set_nor_wrote_off_fails():
    ours = {'deploy/onprem/backend.env.base.example': 'STORAGE_BACKEND=mongo\n'}
    result = _MODULE.check(UPSTREAM, ours, {})
    assert 'MEMORY_ENABLED' in result['undeclared']
    assert 'STORAGE_BACKEND' not in result['undeclared']


def test_declaring_it_clears_it():
    ours = {'deploy/onprem/backend.env.base.example': 'STORAGE_BACKEND=mongo\nMEMORY_ENABLED=on\n'}
    assert 'MEMORY_ENABLED' not in _MODULE.check(UPSTREAM, ours, {})['undeclared']


def test_a_written_off_variable_clears_it_too():
    ours = {'deploy/onprem/backend.env.base.example': 'STORAGE_BACKEND=mongo\n'}
    baseline = {name: 'reviewed: the default is right for on-prem' for name in _MODULE.upstream_declared(UPSTREAM)}
    del baseline['STORAGE_BACKEND']  # we declare that one
    result = _MODULE.check(UPSTREAM, ours, baseline)
    assert result['undeclared'] == []
    assert result['stale_baseline'] == []


def test_a_baseline_note_that_is_no_longer_needed_is_reported():
    """A ratchet list that only grows rots into the stale residual list that already cost us three
    real failures read as known noise."""
    ours = {'deploy/onprem/backend.env.base.example': 'STORAGE_BACKEND=mongo\nMEMORY_ENABLED=on\n'}
    result = _MODULE.check(UPSTREAM, ours, {'MEMORY_ENABLED': 'unreviewed'})
    assert result['stale_baseline'] == ['MEMORY_ENABLED']


def test_unreviewed_notes_are_counted_as_the_debt():
    baseline = {'A_VAR': _MODULE.UNREVIEWED, 'B_VAR': 'default-ok, verified: ...'}
    assert _MODULE.check('', {}, baseline)['unreviewed'] == ['A_VAR']


def test_baseline_shape_is_validated(tmp_path):
    good = tmp_path / 'good.json'
    good.write_text(json.dumps({'A_VAR': 'a note'}))
    assert _MODULE.load_baseline(good) == {'A_VAR': 'a note'}
    assert _MODULE.load_baseline(tmp_path / 'absent.json') == {}

    blank = tmp_path / 'blank.json'
    blank.write_text('   ')
    with pytest.raises(ValueError, match='empty'):
        _MODULE.load_baseline(blank)

    empty_note = tmp_path / 'empty_note.json'
    empty_note.write_text(json.dumps({'A_VAR': '  '}))
    with pytest.raises(ValueError, match='nonempty-note'):
        _MODULE.load_baseline(empty_note)


def test_the_repository_is_at_or_below_its_baseline():
    """The ratchet itself, on the real tree — the check CI runs."""
    root = Path(__file__).resolve().parents[3]
    upstream_text, our_texts = _MODULE._read(root)
    baseline = _MODULE.load_baseline(root / _MODULE.DEFAULT_BASELINE)
    result = _MODULE.check(upstream_text, our_texts, baseline)
    assert result['undeclared'] == []
    assert result['stale_baseline'] == []


def test_the_two_measured_gaps_are_now_DECLARED_not_merely_annotated():
    """The successor of "these two carry a real note".

    `MEMORY_ENABLED` and `MEMORY_V3_CURSOR_SECRET` were the two gaps proven on live storage, and the
    original assertion demanded a written finding instead of the `unreviewed` default. Both have since been
    **declared** in our env-file and in the chart (ADR-0063/ADR-0064 work), which is the outcome the note
    was pointing at — and the baseline self-cleans, so a declared name leaves it. Asserting they are ABSENT
    keeps the guarantee where annotating them no longer can: if either is ever dropped from our declarations
    it reappears in the baseline as `unreviewed`, and this fails.
    """
    root = Path(__file__).resolve().parents[3]
    baseline = _MODULE.load_baseline(root / _MODULE.DEFAULT_BASELINE)
    for name in ('MEMORY_ENABLED', 'MEMORY_V3_CURSOR_SECRET'):
        assert name not in baseline, f'{name} is undeclared again — declare it, do not annotate it'


def test_every_baseline_entry_that_carries_a_note_keeps_it():
    """The ratchet's other half: a note, once written, must not silently decay to `unreviewed`."""
    root = Path(__file__).resolve().parents[3]
    baseline = _MODULE.load_baseline(root / _MODULE.DEFAULT_BASELINE)
    annotated = {name: note for name, note in baseline.items() if note != _MODULE.UNREVIEWED}
    assert all(note.strip() for note in annotated.values()), 'a blank note is not a note'
