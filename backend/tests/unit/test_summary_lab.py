from __future__ import annotations

import json
import sys
from pathlib import Path

from testing.summary_lab.cli import main as cli_main
from testing.summary_lab.compare import compare_variants
from testing.summary_lab.fixtures import load_synthetic_fixtures
from testing.summary_lab.judge import score_note
from testing.summary_lab.pricing import estimate_usd
from testing.summary_lab.render import render_lab_html
from testing.summary_lab.runner import run_matrix
from testing.summary_lab.seams import MissingRecordedNote, recorded_seam
from testing.summary_lab.variants import VARIANTS


def test_synthetic_fixtures_are_committable_and_nonempty() -> None:
    fixtures = load_synthetic_fixtures()
    assert len(fixtures) >= 6
    ids = {fixture.id for fixture in fixtures}
    assert 'playback-commute' in ids
    assert 'filler-decision' in ids
    for fixture in fixtures:
        assert fixture.transcript.strip()
        assert 'notes_v2' in fixture.recorded
        assert 'defective' in fixture.recorded
        assert '@' not in fixture.transcript


def test_judge_rewards_owner_useful_notes_and_penalizes_playback_filler() -> None:
    fixtures = {fixture.id: fixture for fixture in load_synthetic_fixtures()}
    commute = fixtures['playback-commute']
    good = score_note(
        commute.recorded['notes_v2'],
        expected_facts=commute.expected_facts,
        must_not_contain=commute.must_not_contain,
    )
    bad = score_note(
        commute.recorded['defective'],
        expected_facts=commute.expected_facts,
        must_not_contain=commute.must_not_contain,
    )
    assert good.usefulness >= 0.8
    assert good.playback_hits == 0
    assert bad.usefulness < good.usefulness
    assert bad.playback_hits >= 1
    assert any(defect.startswith('playback:') or defect.startswith('forbidden:') for defect in bad.defects)


def test_pricing_is_linear_and_non_negative() -> None:
    cheap = estimate_usd(1_000, 200)
    twice = estimate_usd(2_000, 400)
    assert cheap.usd > 0
    assert abs(twice.usd - 2 * cheap.usd) < 1e-9


def test_recorded_matrix_scores_notes_v2_above_defective() -> None:
    run = run_matrix(load_synthetic_fixtures())
    by_variant: dict[str, list[float]] = {}
    for cell in run.cells:
        by_variant.setdefault(cell.variant_id, []).append(cell.judge.usefulness)
    notes_mean = sum(by_variant['notes_v2_recorded']) / len(by_variant['notes_v2_recorded'])
    defective_mean = sum(by_variant['defective_recorded']) / len(by_variant['defective_recorded'])
    assert notes_mean > defective_mean
    assert run.total_usd > 0


def test_compare_reports_usefulness_gain_for_notes_v2_over_defective() -> None:
    run = run_matrix(load_synthetic_fixtures())
    report = compare_variants(run, 'defective_recorded', 'notes_v2_recorded')
    assert report.mean_usefulness_delta > 0


def test_html_renderer_includes_scores() -> None:
    run = run_matrix(load_synthetic_fixtures(), (VARIANTS[0],))
    page = render_lab_html(run)
    assert '<table>' in page
    assert 'usefulness' in page
    assert run.cells[0].fixture_id in page


def test_cli_run_writes_json_and_html(tmp_path: Path) -> None:
    out = tmp_path / 'lab'
    assert cli_main(['run', '--out', str(out)]) == 0
    payload = json.loads((out / 'run.json').read_text(encoding='utf-8'))
    assert payload['cells']
    html = (out / 'lab.html').read_text(encoding='utf-8')
    assert 'summary lab' in html
    summary = (out / 'summary.txt').read_text(encoding='utf-8')
    assert 'mean_usefulness=' in summary


def test_recorded_seam_requires_variant_key() -> None:
    fixture = load_synthetic_fixtures()[0]
    missing = VARIANTS[0]
    broken = type(missing)(id='x', recorded_key='not-a-key', description='x')
    try:
        recorded_seam(fixture, broken)
        raise AssertionError('expected MissingRecordedNote')
    except MissingRecordedNote:
        pass


def test_harness_import_does_not_load_production_summarizer() -> None:
    loaded = {name for name in sys.modules if name.startswith('utils.llm.conversation_processing')}
    assert not loaded
