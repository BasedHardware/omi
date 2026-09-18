from __future__ import annotations

import importlib.util
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "jit_qa_typesense_key_shape.py"
KEY = b"a" * 64
spec = importlib.util.spec_from_file_location("jit_qa_typesense_key_shape_for_test", SCRIPT)
assert spec is not None and spec.loader is not None
KEY_SHAPE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(KEY_SHAPE)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (KEY, "valid"),
        (KEY + b"\n", "legacy_trailing_lf"),
        (KEY + b"\r\n", "invalid"),
        (KEY.upper(), "invalid"),
        (KEY[:-1], "invalid"),
        (KEY + b" ", "invalid"),
    ],
)
def test_key_shape_is_strict_and_content_free(value: bytes, expected: str):
    assert KEY_SHAPE.classify_typesense_api_key(value) == expected
    if expected == "invalid":
        with pytest.raises(ValueError, match="unexpected byte shape"):
            KEY_SHAPE.normalize_typesense_api_key(value)


def test_normalize_stdin_repairs_only_the_known_legacy_newline_shape():
    legacy = KEY + b"\n"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--normalize-stdin"],
        input=legacy,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    assert completed.stdout == KEY
    assert completed.stderr == b""


def test_normalize_stdin_accepts_exact_key_without_adding_bytes():
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--normalize-stdin"],
        input=KEY,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    assert completed.stdout == KEY
    assert completed.stderr == b""


def test_file_mode_reports_repair_status_for_set_e_shell_boundary(tmp_path: Path):
    """The workflow must capture the helper's intentional exit-2 status."""
    raw = tmp_path / "raw"
    normalized = tmp_path / "normalized"
    raw.write_bytes(KEY + b"\n")
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--normalize-file", str(raw), "--output", str(normalized)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode == 2
    assert completed.stdout == b"legacy_trailing_lf\n"
    assert completed.stderr == b""
    assert normalized.read_bytes() == KEY
    assert normalized.stat().st_mode & 0o777 == 0o600
    assert KEY not in completed.stdout
    assert KEY not in completed.stderr


def test_bash_boundary_captures_repair_status_under_set_e(tmp_path: Path):
    raw = tmp_path / "raw"
    normalized = tmp_path / "normalized"
    raw.write_bytes(KEY + b"\n")
    raw_arg = shlex.quote(str(raw))
    normalized_arg = shlex.quote(str(normalized))
    script_arg = shlex.quote(str(SCRIPT))
    shell = f"""
set -euo pipefail
set +e
shape="$(python3 {script_arg} --normalize-file {raw_arg} --output {normalized_arg})"
status=$?
set -e
case "$status:$shape" in
  2:legacy_trailing_lf) ;;
  *) exit 1 ;;
esac
"""
    completed = subprocess.run(
        ["/bin/bash", "-c", shell],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr.decode()
    assert normalized.read_bytes() == KEY
