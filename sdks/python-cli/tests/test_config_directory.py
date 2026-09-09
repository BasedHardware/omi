import os
import stat

import pytest

from omi_cli import config as cfg

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX directory modes")


@pytest.mark.parametrize("mode", [0o750, 0o775, 0o2770])
@pytest.mark.parametrize("symlink", [False, True])
def test_save_preserves_existing_parent(tmp_path, mode, symlink):
    directory = tmp_path / "shared"
    directory.mkdir()
    directory.chmod(mode)
    before = stat.S_IMODE(directory.stat().st_mode)
    parent = directory
    if symlink:
        parent = tmp_path / "link"
        parent.symlink_to(directory, target_is_directory=True)
    path = parent / "config.toml"
    cfg.save(cfg.Config(path=path))
    assert stat.S_IMODE(directory.stat().st_mode) == before
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("parts", [(".omi",), (".config", "omi", "profiles")])
def test_new_directory_and_file_are_private(tmp_path, monkeypatch, parts):
    path = tmp_path.joinpath(*parts, "config.toml")
    original = cfg.tomli_w.dump

    def inspect(payload, handle):
        assert stat.S_IMODE(os.fstat(handle.fileno()).st_mode) == 0o600
        original(payload, handle)

    monkeypatch.setattr(cfg.tomli_w, "dump", inspect)
    cfg.save(cfg.Config(path=path))
    for parent in path.parents:
        if parent == tmp_path:
            break
        assert stat.S_IMODE(parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_failed_save_does_not_chmod_parent(tmp_path, monkeypatch):
    tmp_path.chmod(0o750)

    def fail(*args):
        raise ValueError("synthetic failure")

    monkeypatch.setattr(cfg.tomli_w, "dump", fail)
    with pytest.raises(ValueError):
        cfg.save(cfg.Config(path=tmp_path / "config.toml"))
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o750
