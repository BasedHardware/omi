"""Static contract: the backend image ships precompiled first-party bytecode.

Cloud Run cold starts of backend, backend-sync, backend-sync-backfill and
backend-integration spend most of their time importing ``main``. site-packages
is compiled by ``uv pip sync --compile-bytecode`` in the builder stage, but the
``COPY backend/ .`` tree was not, so each new instance recompiled ~800 imported
first-party modules before uvicorn bound its port. This keeps the compile step
in the final stage, after the source copy and before the non-root user switch.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = ROOT / "backend" / "Dockerfile"


def _final_stage_lines() -> list[str]:
    lines = DOCKERFILE.read_text(encoding="utf-8").splitlines()
    last_from = max(i for i, line in enumerate(lines) if line.startswith("FROM "))
    return lines[last_from + 1 :]


def _index(lines: list[str], predicate) -> int:
    matches = [i for i, line in enumerate(lines) if predicate(line)]
    assert matches, "expected instruction not found in the final Dockerfile stage"
    return matches[0]


def test_final_stage_precompiles_app_bytecode_after_source_copy():
    lines = _final_stage_lines()
    copy_source = _index(lines, lambda line: line.strip() == "COPY backend/ .")
    compile_step = _index(lines, lambda line: "python -m compileall" in line and "/app" in line)
    user_switch = _index(lines, lambda line: line.strip() == "USER omi")

    assert copy_source < compile_step < user_switch


def test_bytecode_compile_fails_the_build_on_error():
    compile_line = next(line for line in _final_stage_lines() if "python -m compileall" in line)
    # A syntax error must break the image build, not ship a module that only
    # fails when a request first imports it.
    assert "|| true" not in compile_line
    assert "-q" in compile_line.split()
