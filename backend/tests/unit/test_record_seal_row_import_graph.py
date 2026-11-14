"""The per-row repair process must not import the web framework.

Each seal row is a disposable ``python scripts/record_seal_repair_job.py --row``
subprocess. Measured 2026-11-10, ~88% of the ~89 s per-row time was process
startup plus client construction, and fastapi/pydantic was ~60% of the import
bill. A recording seal needs no web framework, so the row graph is asserted
here rather than left to drift back in through a shared metrics or sync helper.
"""

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]

# Import the row entrypoint exactly as the coordinator launches it, then report
# which heavy web modules the graph pulled in.
_ROW_IMPORT_PROBE = """
import sys
import scripts.record_seal_repair_job  # noqa: F401
print('fastapi' in sys.modules, 'pydantic' in sys.modules, 'starlette' in sys.modules)
"""


def _run(code: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, '-c', code],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_row_entrypoint_import_graph_excludes_the_web_framework():
    result = _run(_ROW_IMPORT_PROBE)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'False False False', result.stdout


def test_row_module_import_graph_excludes_the_web_framework():
    # The coordinator imports this module in-process for discovery; it must stay
    # as cheap as the row child.
    result = _run(
        'import sys; import utils.batch_pipeline.record_seal_cluster_repair;'
        " print('fastapi' in sys.modules, 'pydantic' in sys.modules, 'starlette' in sys.modules)"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'False False False', result.stdout


def test_metrics_route_still_serves_the_web_framework_response():
    # The lazy import must not change the /metrics contract.
    result = _run(
        'from utils.metrics import metrics_response;'
        ' response = metrics_response();'
        " print(type(response).__module__, response.media_type, 'omi_' in response.body.decode())"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'starlette.responses text/plain; version=0.0.4; charset=utf-8 True'


def test_sync_stage_http_dependency_still_raises_http_exception():
    result = _run(
        'import os;'
        " os.environ['OMI_ENV_STAGE'] = 'not-a-stage';"
        ' from fastapi import HTTPException;'
        ' from utils.sync.stage import require_http_stage;'
        ' require_http_stage()'
    )
    assert result.returncode != 0
    assert 'HTTPException' in result.stderr
    assert '503' in result.stderr


def test_successful_sync_stage_check_does_not_import_the_web_framework():
    result = _run(
        'import os, sys;'
        " os.environ['OMI_ENV_STAGE'] = 'prod';"
        ' from utils.sync.stage import require_http_stage;'
        ' require_http_stage();'
        " print('fastapi' in sys.modules, 'pydantic' in sys.modules, 'starlette' in sys.modules)"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'False False False', result.stdout
