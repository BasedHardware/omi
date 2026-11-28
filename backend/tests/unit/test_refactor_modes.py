import pytest

from config import refactor_modes as rm


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for key in ('X_MODE', 'X_MODE_SERVE_PERCENT', 'X_MODE_SERVE_UID_SHA256S', 'X_MODE_SHADOW_PERCENT', 'K'):
        monkeypatch.delenv(key, raising=False)
    rm._warned.clear()


def test_mode_parses_words_and_keeps_default_on_typo(monkeypatch):
    assert rm.mode('X_MODE') == 'off'
    monkeypatch.setenv('X_MODE', 'SERVE')
    assert rm.mode('X_MODE') == 'serve'
    monkeypatch.setenv('X_MODE', 'srve')
    assert rm.mode('X_MODE') == 'off'
    assert rm.mode('X_MODE', default='shadow') == 'shadow'


def test_unset_mode_is_off_unless_frozen_legacy_family(monkeypatch):
    monkeypatch.delenv('LIFECYCLE_V2_MODE', raising=False)
    assert rm.mode('X_MODE') == 'off'
    assert rm.shadow_or_serve('X_MODE') is False
    assert rm.mode('LIFECYCLE_V2_MODE') == 'shadow'
    assert rm.mode('LIFECYCLE_V2_MODE', default='off') == 'off'


# R-20261128-01 (proposed): the legacy implicit-shadow set may only shrink. Remove a name
# here and in refactor_modes when its family is bound, served or retired; never add one.
LEGACY_SHADOW_CEILING = frozenset(
    {
        'CALLS_RECAP_MODE',
        'CAPTURE_COVERAGE_MODE',
        'LIFECYCLE_V2_MODE',
        'NOTES_PACKET_V2_MODE',
        'SPEAKER_EVIDENCE_MODE',
    }
)


def test_legacy_shadow_default_only_shrinks():
    assert rm._LEGACY_SHADOW_DEFAULT <= LEGACY_SHADOW_CEILING


@pytest.mark.parametrize(
    'raw,on,off',
    [
        ('', True, False),
        ('false', False, False),
        ('0', False, False),
        ('true', True, True),
        ('on', True, True),
        ('FLASE', True, False),
    ],
)
def test_default_on_and_off_treat_typos_as_their_default(monkeypatch, raw, on, off):
    monkeypatch.setenv('K', raw)
    assert rm.default_on('K') is on
    assert rm.default_off('K') is off


def test_serving_for_cohort_by_digest_and_percent(monkeypatch):
    monkeypatch.setenv('X_MODE', 'shadow')
    assert rm.serving_for('X_MODE', 'u1') is False
    monkeypatch.setenv('X_MODE_SERVE_UID_SHA256S', rm.uid_digest('u1'))
    assert rm.serving_for('X_MODE', 'u1') is True
    assert rm.serving_for('X_MODE', 'u2') is False
    monkeypatch.setenv('X_MODE_SERVE_PERCENT', '100')
    assert rm.serving_for('X_MODE', 'u2') is True
    monkeypatch.setenv('X_MODE', 'off')
    assert rm.serving_for('X_MODE', 'u1') is False
    monkeypatch.setenv('X_MODE', 'serve')
    assert rm.serving_for('X_MODE', None) is True


def test_wave2_percentage_cohorts_align_and_expand_monotonically():
    previous = set()
    for percent in (1, 5, 25, 100):
        env = {f'{name}_SERVE_PERCENT': str(percent) for name in rm.WAVE2_MODES}
        env.update({name: 'shadow' for name in rm.WAVE2_MODES})
        selected = set()
        for index in range(1000):
            account = f'synthetic-{index}'
            decisions = {rm.serving_for(name, account, environ=env) for name in rm.WAVE2_MODES}
            assert len(decisions) == 1
            if decisions == {True}:
                selected.add(account)
        assert previous <= selected
        assert selected
        previous = selected
    assert len(previous) == 1000


def test_wave2_digest_pilot_and_off_rollback_override_aligned_percent():
    for name in rm.WAVE2_MODES:
        env = {name: 'shadow', f'{name}_SERVE_UID_SHA256S': rm.uid_digest('synthetic-pilot')}
        assert rm.serving_for(name, 'synthetic-pilot', environ=env)
        assert not rm.serving_for(name, 'synthetic-control', environ=env)
        env[name] = 'off'
        assert not rm.serving_for(name, 'synthetic-pilot', environ=env)


def test_shadow_or_serve(monkeypatch):
    assert rm.shadow_or_serve('X_MODE') is False
    monkeypatch.setenv('X_MODE', 'shadow')
    assert rm.shadow_or_serve('X_MODE') is True
    monkeypatch.setenv('X_MODE', 'off')
    assert rm.shadow_or_serve('X_MODE') is False


def test_shadow_sampled_keeps_cohort_and_samples_others(monkeypatch):
    monkeypatch.delenv('X_MODE_SHADOW_PERCENT', raising=False)
    monkeypatch.setenv('X_MODE', 'shadow')
    assert rm.shadow_sampled('X_MODE', 'u1', 0) is False
    assert rm.shadow_sampled('X_MODE', 'u1', 100) is True
    monkeypatch.setenv('X_MODE_SERVE_UID_SHA256S', rm.uid_digest('u1'))
    assert rm.shadow_sampled('X_MODE', 'u1', 0) is True
    monkeypatch.setenv('X_MODE_SHADOW_PERCENT', '100')
    assert rm.shadow_sampled('X_MODE', 'u2', 0) is True
    monkeypatch.setenv('X_MODE', 'off')
    assert rm.shadow_sampled('X_MODE', 'u2', 100) is False
    monkeypatch.setenv('X_MODE', 'serve')
    assert rm.shadow_sampled('X_MODE', 'u2', 0) is True


@pytest.mark.parametrize('raw', ['nan', 'inf', '-1', '101', 'typo'])
def test_shadow_invalid_sample_keeps_bounded_default(monkeypatch, raw):
    monkeypatch.setenv('X_MODE', 'shadow')
    monkeypatch.setenv('X_MODE_SHADOW_PERCENT', raw)
    assert not rm.shadow_sampled('X_MODE', 'sample', 0)
    assert rm.shadow_sampled('X_MODE', 'sample', 100)


def test_expired_shadow_reads_as_off_and_serve_is_untouched(monkeypatch, caplog):
    from datetime import date

    monkeypatch.setattr(rm, 'SHADOW_EXPIRES', {'EXPIRY_FIXTURE_MODE': '2026-12-18'})
    monkeypatch.setattr(rm, '_expired_logged', set())
    assert rm._shadow_expired('EXPIRY_FIXTURE_MODE', today=date(2026, 12, 17)) is False
    assert rm._shadow_expired('EXPIRY_FIXTURE_MODE', today=date(2026, 12, 18)) is True
    assert rm._shadow_expired('OTHER_MODE', today=date(2030, 1, 1)) is False
    assert 'event=shadow_expired name=EXPIRY_FIXTURE_MODE' in caplog.text

    monkeypatch.setattr(rm, '_shadow_expired', lambda name, today=None: name == 'EXPIRY_FIXTURE_MODE')
    assert rm.mode('EXPIRY_FIXTURE_MODE', environ={'EXPIRY_FIXTURE_MODE': 'shadow'}) == 'off'
    assert rm.mode('EXPIRY_FIXTURE_MODE', environ={'EXPIRY_FIXTURE_MODE': 'serve'}) == 'serve'
    assert rm.mode('OTHER_MODE', environ={'OTHER_MODE': 'shadow'}) == 'shadow'


def test_shadow_expiry_table_shape():
    from config.shadow_expiry import SHADOW_EXPIRES

    assert all(isinstance(key, str) and isinstance(value, str) for key, value in SHADOW_EXPIRES.items())
