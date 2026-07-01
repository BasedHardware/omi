import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
PUSHER_DOCKERFILE = BACKEND_DIR / 'pusher' / 'Dockerfile'


def _pusher_runtime_copy_dirs() -> list[str]:
    pattern = re.compile(r'^COPY\s+backend/([^/\s]+)/\s+\./\1/$')
    copied_dirs: list[str] = []
    for line in PUSHER_DOCKERFILE.read_text(encoding='utf-8').splitlines():
        match = pattern.match(line.strip())
        if match:
            copied_dirs.append(match.group(1))
    return copied_dirs


def test_pusher_image_layout_includes_backend_config_imports(tmp_path):
    copied_dirs = _pusher_runtime_copy_dirs()
    assert 'config' in copied_dirs

    for dirname in copied_dirs:
        shutil.copytree(BACKEND_DIR / dirname, tmp_path / dirname)

    env = {**os.environ, 'PYTHONPATH': str(tmp_path)}
    result = subprocess.run(
        [sys.executable, '-c', 'import config.memory_confidence'],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
