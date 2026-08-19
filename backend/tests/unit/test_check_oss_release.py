"""Tests for the release guard (ADR-0054).

The rule under test: one source for OMI_OSS_RELEASE, it stays tracked by git, and every image we build
carries it instead of a mutable literal tag. These assert the FAILURES the guard must catch.
"""

import importlib.util
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = _REPO / '.github' / 'scripts' / 'check_oss_release.py'
if not _SCRIPT.exists():
    # Repo-root guard script — absent when only backend/ is mounted (the offline test image).
    pytest.skip(f'guard script not present at {_SCRIPT}', allow_module_level=True)
_SPEC = importlib.util.spec_from_file_location('check_oss_release', _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

RELEASE = 'OMI_OSS_RELEASE=0.2.0\n'
GITIGNORE = '.env\n!omi.oss.release.env\n'
COMPOSE = {
    'compose.base.yaml': '    image: omi-oss-backend:${OMI_OSS_RELEASE:?release not set}\n'
                         '    image: ${OMI_OSS_MONGO_IMAGE:?pin missing}\n',
}


def test_aligned_tree_passes():
    assert _MODULE.check(RELEASE, COMPOSE, GITIGNORE) == []


def test_literal_latest_on_an_image_we_build_is_flagged():
    # The regression the whole design prevents: a rebuild silently reusing a mutable tag.
    compose = {'compose.base.yaml': '    image: omi-oss-backend:latest\n'}
    problems = _MODULE.check(RELEASE, compose, GITIGNORE)
    assert any('not tagged with the release' in p for p in problems), problems


def test_pinned_literal_version_on_an_image_we_build_is_also_flagged():
    # Hardcoding the number defeats the single source just as much as :latest does.
    compose = {'compose.base.yaml': '    image: omi-oss-whisper:0.2.0\n'}
    problems = _MODULE.check(RELEASE, compose, GITIGNORE)
    assert any('not tagged with the release' in p for p in problems), problems


def test_third_party_pins_are_not_touched_by_this_guard():
    compose = {'compose.base.yaml': '    image: ${OMI_OSS_MONGO_IMAGE:?pin missing}\n    image: mongo:7\n'}
    assert _MODULE.check(RELEASE, compose, GITIGNORE) == []


def test_missing_gitignore_negation_is_flagged():
    problems = _MODULE.check(RELEASE, COMPOSE, '.env\n')
    assert any('missing `!omi.oss.release.env`' in p for p in problems), problems


def test_non_semver_release_is_flagged():
    problems = _MODULE.check('OMI_OSS_RELEASE=latest\n', COMPOSE, GITIGNORE)
    assert any('is not SemVer' in p for p in problems), problems


def test_missing_release_line_is_flagged():
    problems = _MODULE.check('# nothing here\n', COMPOSE, GITIGNORE)
    assert any(f'no {_MODULE.VAR}=' in p for p in problems), problems


def test_prerelease_suffix_is_accepted():
    assert _MODULE.check('OMI_OSS_RELEASE=0.3.0-rc.1\n', COMPOSE, GITIGNORE) == []


def test_the_real_repo_is_aligned():
    """The check as CI runs it — the tree in this commit must pass."""
    assert _MODULE.main() == 0
