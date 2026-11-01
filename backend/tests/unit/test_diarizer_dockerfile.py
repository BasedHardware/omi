from pathlib import Path

import pytest


@pytest.mark.parametrize('filename', ['Dockerfile', 'Dockerfile.batch-pipeline'])
def test_diarizer_runtime_library_path_includes_gke_driver_and_ffmpeg_libs(filename):
    dockerfile = Path(__file__).resolve().parents[2] / 'diarizer' / filename
    contents = dockerfile.read_text()

    assert 'ENV PATH="/usr/local/nvidia/bin:' in contents
    assert 'ENV LD_LIBRARY_PATH="/usr/local/nvidia/lib:/usr/local/nvidia/lib64:/usr/lib/x86_64-linux-gnu"' in contents


def test_diarizer_dockerfile_has_no_backslash_space_continuations():
    dockerfile = Path(__file__).resolve().parents[2] / 'diarizer' / 'Dockerfile'

    for line in dockerfile.read_text().splitlines():
        assert not line.endswith('\\ ')
