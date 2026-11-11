"""Scanner contract for the storm-alignment parity gate.

Pins the real scanner's verdict rules on synthetic modules (every rule
class, hostile inputs, the no-escape closure rule, ablation semantics) and
the CLI's exit codes, plus the family inventory pins: every family file
exists, parses, and the landed family scans clean in the fixed posture
while dealignment flags exactly the publication re-strike lane.

Failure-Class: FC-publication-restrike-collides-inside-the-armed-storm-window
"""

import json

import pytest

import scripts.scan_storm_alignment as scanner_module
from scripts.scan_storm_alignment import (
    ALIGNMENT_CALLS,
    BACKEND_ROOT,
    FAMILY_FILES,
    ablate_source,
    catalog_source,
    main,
    scan_source,
    scan_tree_catalog,
)

FC = 'FC-publication-restrike-collides-inside-the-armed-storm-window'

EXHAUST = 'FirestoreContentionExhausted'

# One full-family scan at import. The fast-unit CPU guard budgets the CALL
# phase at 1.0s per test; a full-family rescan inside a test body burns
# ~2.4s CPU and fails the file, so every family-wide assertion reads this
# import-time cache (the import phase is exempt -- the parity grid fixture
# works the same way).
_FAMILY_CATALOG = scan_tree_catalog()
_FAMILY_FINDINGS = {key: finding for key, finding in _FAMILY_CATALOG.items() if finding}

# A synthetic two-module family for the CLI contract: one aligned lane, one
# bare ladder. Small enough that main() scans it in milliseconds.
ALIGNED_LANE = (
    'def lane(error):\n'
    f'    try:\n'
    f'        pass\n'
    f'    except {EXHAUST}:\n'
    '        time.sleep(contention_retry_after(error))\n'
)
BARE_LANE = 'def lane():\n' f'    try:\n' f'        pass\n' f'    except {EXHAUST}:\n' '        time.sleep(0.5)\n'
TINY_FAMILY = {'utils/batch_pipeline/lane.py': ALIGNED_LANE, 'database/other.py': BARE_LANE}


@pytest.fixture
def tiny_family(tmp_path, monkeypatch):
    """Point the CLI at a two-module family under tmp_path."""
    for rel, source in TINY_FAMILY.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    monkeypatch.setattr(scanner_module, 'FAMILY_FILES', tuple(TINY_FAMILY))
    return tmp_path


@pytest.fixture
def clean_family(tmp_path, monkeypatch):
    """Point the CLI at a single-module family with no findings."""
    rel = 'utils/batch_pipeline/lane.py'
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ALIGNED_LANE)
    monkeypatch.setattr(scanner_module, 'FAMILY_FILES', (rel,))
    return tmp_path


def verdict_for(source: str, module: str = 'probe.py'):
    """The scanner's per-function verdict map for one synthetic module."""
    return catalog_source(source, module)


def test_ablation_renames_every_alignment_helper():
    source = 'def gate(error):\n    return contention_retry_after(error)\n'
    ablated = ablate_source(source)
    assert 'contention_retry_after__dealigned' in ablated
    assert 'contention_retry_after(' not in ablated


def test_ablation_preserves_similarly_named_identifiers():
    source = 'def gate(error):\n    return contention_retry_after_default(error)\n'
    assert ablate_source(source) == source


def test_ablation_is_idempotent():
    source = 'def gate(error):\n    return publication_restrike_storm_after(error)\n'
    once = ablate_source(source)
    assert ablate_source(once) == once


def test_ablation_covers_every_helper_name():
    source = '\n'.join(f'def probe_{name}():\n    return {name}\n' for name in sorted(ALIGNMENT_CALLS))
    ablated = ablate_source(source)
    for name in ALIGNMENT_CALLS:
        assert f'{name}__dealigned' in ablated
        assert f'return {name}\n' not in ablated


def test_typed_catch_with_bare_sleep_is_a_finding():
    source = f'def lane():\n' f'    try:\n' f'        pass\n' f'    except {EXHAUST}:\n' f'        time.sleep(0.5)\n'
    verdicts = verdict_for(source)
    assert verdicts['lane'] is not None
    assert 'bare contention re-offer' in verdicts['lane']


def test_typed_catch_with_alignment_helper_is_clean():
    source = (
        f'def lane(error):\n'
        f'    try:\n'
        f'        pass\n'
        f'    except {EXHAUST}:\n'
        f'        time.sleep(contention_retry_after(error))\n'
    )
    assert verdict_for(source)['lane'] is None


def test_typed_catch_with_stamped_attribute_read_is_clean():
    source = (
        f'def lane(error):\n'
        f'    try:\n'
        f'        pass\n'
        f'    except {EXHAUST}:\n'
        f'        time.sleep(error.retry_after)\n'
    )
    assert verdict_for(source)['lane'] is None


def test_deferral_contract_keyword_is_surface_and_alignment():
    source = (
        f'def lane(error):\n'
        f'    try:\n'
        f'        pass\n'
        f'    except Exception:\n'
        f'        defer(owner, retry_after=contention_retry_after(error))\n'
        f'    await asyncio.sleep(0.5)\n'
    )
    assert verdict_for(source)['lane'] is None


def test_catch_without_wait_is_the_cadence_shape_and_clean():
    source = (
        f'def lane():\n'
        f'    try:\n'
        f'        pass\n'
        f'    except {EXHAUST}:\n'
        f'        logger.warning("event=batch_recover outcome=retry")\n'
    )
    assert verdict_for(source)['lane'] is None


def test_classifier_call_with_bare_sleep_is_a_finding():
    source = 'def lane(error):\n' '    if publication_loss_is_contention(error):\n' '        time.sleep(0.25)\n'
    assert verdict_for(source)['lane'] is not None


def test_error_type_string_compare_with_bare_sleep_is_a_finding():
    source = (
        "def lane(error):\n"
        "    if error_type(error) == 'FirestoreContentionExhausted':\n"
        "        time.sleep(0.25)\n"
    )
    assert verdict_for(source)['lane'] is not None


def test_construction_site_stamping_retry_after_is_clean():
    source = (
        f'def lane(last):\n'
        f'    applied = 0.2\n'
        f'    for attempt in range(8):\n'
        f'        if attempt:\n'
        f'            time.sleep(applied)\n'
        f'    error = JobStoreContentionExhausted("kept conflicting", retry_after=applied)\n'
        f'    raise error from last\n'
    )
    assert verdict_for(source)['lane'] is None


def test_retry_engine_gate_shape_is_clean():
    source = (
        'def lane(attempt, inter_attempt_gate=None):\n'
        f'    try:\n'
        f'        pass\n'
        f'    except {EXHAUST}:\n'
        '        if inter_attempt_gate is not None:\n'
        '            time.sleep(normalized_gate_seconds(inter_attempt_gate(attempt)))\n'
    )
    assert verdict_for(source)['lane'] is None


def test_bare_ladder_cannot_hide_behind_a_closure():
    source = (
        f'def lane():\n'
        f'    def rerun():\n'
        f'        time.sleep(0.5)\n'
        f'    try:\n'
        f'        pass\n'
        f'    except {EXHAUST}:\n'
        f'        rerun()\n'
    )
    assert verdict_for(source)['lane'] is not None


def test_nested_def_is_judged_on_its_own_too():
    source = (
        f'def lane():\n'
        f'    def rerun(error):\n'
        f'        try:\n'
        f'            pass\n'
        f'        except {EXHAUST}:\n'
        f'            time.sleep(0.5)\n'
        f'    return rerun\n'
    )
    assert verdict_for(source)['lane.rerun'] is not None


def test_async_lane_follows_the_same_rules():
    source = (
        f'async def lane(error):\n'
        f'    try:\n'
        f'        pass\n'
        f'    except {EXHAUST}:\n'
        f'        await self._publication_sleep(0.25)\n'
    )
    assert verdict_for(source)['lane'] is not None

    source_aligned = source.replace(
        'await self._publication_sleep(0.25)', 'await asyncio.sleep(publication_restrike_storm_after(error))'
    )
    assert verdict_for(source_aligned)['lane'] is None


def test_clean_functions_get_none_entries_in_the_catalog():
    source = 'def unrelated():\n    return 1\n\n\ndef other():\n    return 2\n'
    catalog = verdict_for(source)
    assert catalog == {'unrelated': None, 'other': None}


def test_scan_source_returns_only_flagged_entries():
    source = (
        f'def bare():\n'
        f'    try:\n'
        f'        pass\n'
        f'    except {EXHAUST}:\n'
        f'        time.sleep(0.5)\n'
        f'\n'
        f'def clean():\n'
        f'    return 1\n'
    )
    findings = scan_source(source, 'probe.py')
    assert set(findings) == {'bare'}


def test_unparsable_source_is_reported_not_swallowed():
    catalog = catalog_source('def broken(:\n', 'broken.py')
    assert '<module:broken.py>' in catalog
    assert 'unparsable' in catalog['<module:broken.py>']


def test_every_family_file_exists():
    for rel in FAMILY_FILES:
        assert (BACKEND_ROOT / rel).is_file(), rel


def test_every_family_file_parses():
    bad = [key for key in _FAMILY_CATALOG if key.startswith('<module:')]
    assert not bad, bad


def test_family_files_are_deterministic_and_anchored():
    assert FAMILY_FILES == tuple(FAMILY_FILES)
    assert all(not rel.startswith('/') for rel in FAMILY_FILES)
    assert any(rel.endswith('database/batch_pipeline_store.py') for rel in FAMILY_FILES)


def test_landed_family_scans_clean():
    assert _FAMILY_FINDINGS == {}


def test_scan_tree_reports_missing_files():
    findings = scan_tree_catalog(BACKEND_ROOT, ['database/does_not_exist.py'])
    assert '<missing:database/does_not_exist.py>' in findings


def test_tree_catalog_agrees_with_per_file_catalog():
    """One probe module re-scanned alone matches the import-time family catalog."""
    probe = 'database/_client.py'
    assert scan_tree_catalog(BACKEND_ROOT, [probe]) == {
        key: finding for key, finding in _FAMILY_CATALOG.items() if key.startswith(probe + '::')
    }


def test_cli_exits_clean_on_a_clean_family(clean_family, capsys):
    assert main(['--root', str(clean_family)]) == 0
    assert '0 finding(s)' in capsys.readouterr().out


def test_cli_flags_the_bare_ladder(tiny_family, capsys):
    assert main(['--root', str(tiny_family)]) == 1
    out = capsys.readouterr().out
    assert 'database/other.py::lane' in out
    assert 'bare contention re-offer' in out


def test_cli_ablation_flips_the_aligned_lane(clean_family, capsys):
    assert main(['--root', str(clean_family)]) == 0
    assert main(['--root', str(clean_family), '--ablate']) == 1
    out = capsys.readouterr().out
    assert 'utils/batch_pipeline/lane.py::lane' in out
    assert '(ablated posture)' in out


def test_cli_json_emits_parseable_findings(tiny_family, capsys):
    assert main(['--root', str(tiny_family), '--json']) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload['ablated'] is False
    assert 'database/other.py::lane' in payload['findings']


def test_cli_rejects_unknown_flags():
    with pytest.raises(SystemExit) as excinfo:
        main(['--no-such-flag'])
    assert excinfo.value.code == 2
