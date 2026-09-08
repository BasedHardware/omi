"""Fixture tests for the #9571/#9600 datetime sort-sentinel static tripwire."""

from __future__ import annotations

from pathlib import Path
import tempfile

from scripts import check_datetime_sort_sentinel_ratchet as ratchet

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "datetime_sort_sentinel_ratchet"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_allows_timezone_aware_sort_sentinels():
    assert ratchet.findings(fixture("accepted_aware_sentinels.py"), "accepted_aware_sentinels.py") == []


def test_rejects_naive_min_and_max_sort_sentinels_at_their_exact_lines():
    findings = ratchet.findings(fixture("rejected_naive_sentinels.py"), "rejected_naive_sentinels.py")

    assert [(finding.line, finding.sentinel) for finding in findings] == [(5, "min"), (9, "max")]


def test_rejects_module_qualified_datetime_sentinel():
    findings = ratchet.findings(fixture("rejected_module_alias.py"), "rejected_module_alias.py")

    assert [(finding.line, finding.sentinel) for finding in findings] == [(5, "max")]


def test_ignores_naive_datetime_bounds_outside_inline_sort_keys():
    source = """
from datetime import datetime

LOWEST = datetime.min

def value():
    return LOWEST
"""

    assert ratchet.findings(source) == []


def test_diagnostic_cites_real_incidents_and_timezone_aware_pattern():
    assert "#9571" in ratchet.SORT_SENTINEL_GUIDANCE
    assert "#9600" in ratchet.SORT_SENTINEL_GUIDANCE
    assert "datetime.min.replace(tzinfo=timezone.utc)" in ratchet.SORT_SENTINEL_GUIDANCE
    assert "static tripwire" in ratchet.SORT_SENTINEL_GUIDANCE


def test_source_files_excludes_hidden_local_tooling_directories():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "backend"
        (source / "routers").mkdir(parents=True)
        (source / "routers" / "safe.py").write_text("from datetime import datetime\n", encoding="utf-8")
        hidden = source / ".openapi-venv" / "lib" / "aenum"
        hidden.mkdir(parents=True)
        (hidden / "_py2.py").write_text("print 'python 2 only'\n", encoding="utf-8")

        assert ratchet.source_files(root) == [source / "routers" / "safe.py"]
