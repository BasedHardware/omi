"""Tests for the third-party image pin check (ADR-0055, supersedes the ADR-0050 parity model).

The rule under test: `deploy/onprem/omi.oss.release.pins` is the single source of truth; compose
references it (never an inline pin) and the Helm values mirror it. These assert the FAILURES the guard
must catch, not only that the current tree passes.
"""

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / '.github' / 'scripts' / 'check_oss_image_parity.py'
if not _SCRIPT.exists():
    # Repo-root guard script — absent when only backend/ is mounted (the offline test image).
    pytest.skip(f'guard script not present at {_SCRIPT}', allow_module_level=True)
_SPEC = importlib.util.spec_from_file_location('check_oss_image_parity', _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _ref(name: str, marker: str | None) -> str:
    """A stand-in image reference that still contains the marker the check looks for in the values."""
    return f'{marker}1.0' if marker else f'{name}:1.0'


# A minimal but complete world: every component the check knows about, pinned once.
PINS = '\n'.join(f'{var}={_ref(name, marker)}' for name, (var, marker) in _MODULE.COMPONENTS.items())

COMPOSE = {
    'compose.base.yaml': '\n'.join(f'    image: ${{{var}:?pin missing}}' for _, (var, _) in _MODULE.COMPONENTS.items()),
}


def _values(**overrides: str) -> str:
    """values.yaml mirroring the pins, with optional per-component drift."""
    return '\n'.join(
        f'  image: {overrides.get(name, _ref(name, marker))}'
        for name, (_, marker) in _MODULE.COMPONENTS.items()
        if marker is not None
    )


def test_aligned_tree_passes():
    assert _MODULE.check(PINS, COMPOSE, _values()) == []


def test_helm_drifting_from_the_pins_is_flagged():
    problems = _MODULE.check(PINS, COMPOSE, _values(mongo='mongo:2.0'))
    assert any(p.startswith('mongo: DRIFT') for p in problems), problems


def test_inline_third_party_pin_in_compose_is_flagged():
    # The regression this whole design prevents: someone re-pins mongo in the compose file.
    compose = {'compose.base.yaml': COMPOSE['compose.base.yaml'] + '\n    image: mongo:7'}
    problems = _MODULE.check(PINS, compose, _values())
    assert any('inline third-party pin' in p and 'mongo:7' in p for p in problems), problems


def test_our_own_images_are_not_treated_as_third_party():
    # Images we build carry the release (ADR-0054), not a pin — they must not trip rule 2.
    compose = {
        'compose.base.yaml': COMPOSE['compose.base.yaml']
        + '\n    image: omi-oss-backend:latest'
        + '\n    image: omi-oss-whisper:${OMI_OSS_RELEASE:?}'
    }
    assert _MODULE.check(PINS, compose, _values()) == []


def test_reference_to_an_undeclared_pin_is_flagged():
    compose = {'compose.base.yaml': '    image: ${OMI_OSS_TYPO_IMAGE:?pin missing}'}
    problems = _MODULE.check(PINS, compose, _values())
    assert any('OMI_OSS_TYPO_IMAGE' in p and 'absent' in p for p in problems), problems


def test_pin_missing_from_the_file_is_flagged():
    pins = '\n'.join(line for line in PINS.splitlines() if 'MONGO' not in line)
    problems = _MODULE.check(pins, COMPOSE, _values())
    assert any(p.startswith('mongo: OMI_OSS_MONGO_IMAGE missing') for p in problems), problems


def test_pin_nobody_declares_is_flagged():
    problems = _MODULE.check(PINS + '\nOMI_OSS_GHOST_IMAGE=ghost:1', COMPOSE, _values())
    assert any('OMI_OSS_GHOST_IMAGE' in p and 'unknown to this check' in p for p in problems), problems


def test_compose_only_component_must_actually_be_referenced():
    # nginx exists in no Helm values, so nothing else would notice if compose stopped using it.
    compose = {
        'compose.base.yaml': '\n'.join(
            line for line in COMPOSE['compose.base.yaml'].splitlines() if 'NGINX' not in line
        )
    }
    problems = _MODULE.check(PINS, compose, _values())
    assert any('compose-only but no compose file references it' in p for p in problems), problems


def test_a_pin_consumed_only_as_a_build_arg_counts_as_used():
    """A pin can be consumed by a build-arg rather than a service `image:` (the Python base image).

    Rule 4 must see that as usage; otherwise the check calls a live pin dead and the only way to
    silence it is to stop pinning the thing.
    """
    var = _MODULE.COMPONENTS['python-base'][0]
    compose = {
        'compose.base.yaml': '\n'.join(line for line in COMPOSE['compose.base.yaml'].splitlines() if var not in line)
        + f'\n      args:\n        PYTHON_BASE_IMAGE: ${{{var}:?pin missing}}'
    }
    assert _MODULE.check(PINS, compose, _values()) == []


def test_the_real_repo_is_aligned():
    """The check as CI runs it — the tree in this commit must pass."""
    assert _MODULE.main() == 0
