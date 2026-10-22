import pytest

from config import refactor_modes as rm


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for key in ('X_MODE', 'X_MODE_SERVE_PERCENT', 'X_MODE_SERVE_UID_SHA256S', 'X_MODE_SHADOW_PERCENT', 'K'):
        monkeypatch.delenv(key, raising=False)
    rm._warned.clear()


def test_mode_parses_words_and_keeps_default_on_typo(monkeypatch):
    assert rm.mode('X_MODE') == 'shadow'
    monkeypatch.setenv('X_MODE', 'SERVE')
    assert rm.mode('X_MODE') == 'serve'
    monkeypatch.setenv('X_MODE', 'srve')
    assert rm.mode('X_MODE') == 'shadow'
    assert rm.mode('X_MODE', default='off') == 'off'


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


def test_shadow_or_serve(monkeypatch):
    assert rm.shadow_or_serve('X_MODE') is True
    monkeypatch.setenv('X_MODE', 'off')
    assert rm.shadow_or_serve('X_MODE') is False


def test_shadow_sampled_keeps_cohort_and_samples_others(monkeypatch):
    monkeypatch.delenv('X_MODE_SHADOW_PERCENT', raising=False)
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
    monkeypatch.setenv('X_MODE_SHADOW_PERCENT', raw)
    assert not rm.shadow_sampled('X_MODE', 'sample', 0)
    assert rm.shadow_sampled('X_MODE', 'sample', 100)
