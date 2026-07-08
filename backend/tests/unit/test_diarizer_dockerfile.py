from pathlib import Path


def test_diarizer_runtime_library_path_includes_ffmpeg_libs():
    dockerfile = Path(__file__).resolve().parents[2] / 'diarizer' / 'Dockerfile'
    contents = dockerfile.read_text()

    assert '/usr/local/nvidia/lib' in contents
    assert '/usr/local/nvidia/lib64' in contents
    assert '/usr/lib/x86_64-linux-gnu' in contents


def test_diarizer_dockerfile_has_no_backslash_space_continuations():
    dockerfile = Path(__file__).resolve().parents[2] / 'diarizer' / 'Dockerfile'

    for line in dockerfile.read_text().splitlines():
        assert not line.endswith('\\ ')
