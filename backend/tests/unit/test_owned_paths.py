import pytest

from utils.other.owned_paths import owned_scratch_path


def test_scratch_resolution_rejects_traversal_symlinks_and_root(monkeypatch, tmp_path):
    scratch = tmp_path / 'scratch'
    scratch.mkdir()
    outside = tmp_path / 'private'
    outside.mkdir()
    monkeypatch.chdir(scratch)
    monkeypatch.setattr('utils.other.owned_paths.tempfile.gettempdir', lambda: str(scratch / 'system-temp'))
    (scratch / '_temp').mkdir()
    (scratch / '_temp' / 'escape').symlink_to(outside, target_is_directory=True)
    for value in ['_temp/../../private/audio.wav', '_temp/escape/audio.wav', '_temp', str(outside / 'audio.wav')]:
        with pytest.raises(ValueError, match='outside owned scratch'):
            owned_scratch_path(value)
    assert owned_scratch_path('_temp/user.wav') == str(scratch / '_temp/user.wav')
    assert owned_scratch_path('syncing/job/audio.wav') == str(scratch / 'syncing/job/audio.wav')


def test_harness_root_requires_explicit_opt_in(monkeypatch, tmp_path):
    monkeypatch.setattr('utils.other.owned_paths.tempfile.gettempdir', lambda: str(tmp_path / 'system-temp'))
    harness = tmp_path / 'harness'
    monkeypatch.setenv('OMI_HARNESS_STATE_ROOT', str(harness))
    with pytest.raises(ValueError):
        owned_scratch_path(str(harness / 'export.wav'))
    assert owned_scratch_path(str(harness / 'export.wav'), include_harness=True) == str(harness / 'export.wav')
