"""Request-model regressions for timezone admission (#21220).

The two request models that carry a device timezone are validated in-process,
not just at the route: ``SyncUserTimeZoneRequest`` (``PUT /v1/users/time-zone``)
and ``SaveFcmTokenRequest`` (``POST /v1/users/fcm-token``). Both must admit only
zones the daily-summary scheduler can actually serve.

Admission is measured against ``pytz`` — the scheduler/reader authority
(``pytz.all_timezones``, ``pytz.timezone``) — not ``zoneinfo.ZoneInfo``, which
reads the host tz database. ``requirements.txt`` pins ``pytz==2024.1``, so a zone
added to the host tz database afterwards (``America/Coyhaique``, tzdata 2025a) is
accepted by ``ZoneInfo`` and rejected by ``pytz``. Such a zone used to be stored
and then never selected, so the owner silently never received a recap.

Failure class: FC-accepted-input-unschedulable-by-downstream-reader.
"""

import pytz
import pytest
from pydantic import ValidationError

from models.other import SaveFcmTokenRequest, SyncUserTimeZoneRequest

# Zones the pinned pytz accepts; the scheduler can select these.
SCHEDULABLE = [
    'UTC',
    'America/New_York',
    'Europe/London',
    'Asia/Jakarta',
    'Australia/Lord_Howe',  # sub-hour offset: exercises the grouped-by-hour query
]

# Rejected by pytz==2024.1. America/Coyhaique is the tzdata 2025a addition that
# zoneinfo.ZoneInfo accepts on a newer host, which is exactly the silent-miss bug.
UNSCHEDULABLE = [
    'Not/AZone',
    'InvalidZone',
    '',
    '   ',
    '\t',
    'America/Coyhaique',
    'Factory',
    'localtime',
]


def _build(model, **kwargs):
    if model is SaveFcmTokenRequest:
        return model(fcm_token='token-abc', **kwargs)
    return model(**kwargs)


@pytest.mark.parametrize('model', [SyncUserTimeZoneRequest, SaveFcmTokenRequest])
@pytest.mark.parametrize('zone', SCHEDULABLE)
def test_schedulable_zone_is_admitted(model, zone):
    assert _build(model, time_zone=zone).time_zone == zone


@pytest.mark.parametrize('model', [SyncUserTimeZoneRequest, SaveFcmTokenRequest])
@pytest.mark.parametrize('zone', UNSCHEDULABLE)
def test_unschedulable_zone_is_rejected(model, zone):
    with pytest.raises(ValidationError):
        _build(model, time_zone=zone)


@pytest.mark.parametrize('model', [SyncUserTimeZoneRequest, SaveFcmTokenRequest])
def test_surrounding_whitespace_is_trimmed_not_rejected(model):
    """Clients pad the header/body value; the trimmed zone is what gets stored."""
    assert _build(model, time_zone='  America/New_York\n').time_zone == 'America/New_York'
    assert _build(model, time_zone='\tUTC ').time_zone == 'UTC'


@pytest.mark.parametrize('model', [SyncUserTimeZoneRequest, SaveFcmTokenRequest])
def test_empty_string_and_whitespace_only_are_rejected(model):
    with pytest.raises(ValidationError):
        _build(model, time_zone='')
    with pytest.raises(ValidationError):
        _build(model, time_zone=' ' * 8)


@pytest.mark.parametrize('model', [SyncUserTimeZoneRequest, SaveFcmTokenRequest])
def test_rejection_message_names_the_schedulable_contract(model):
    """The 422 detail has to tell the client the zone is unusable, not just invalid."""
    with pytest.raises(ValidationError) as exc:
        _build(model, time_zone='America/Coyhaique')
    assert 'schedulable IANA timezone' in str(exc.value)

    with pytest.raises(ValidationError) as exc:
        _build(model, time_zone='   ')
    assert 'non-empty IANA timezone' in str(exc.value)


def test_coyhaique_is_the_zoneinfo_pytz_divergence_this_guards():
    """Pin the premise: the host admits it, the pinned scheduler authority does not.

    If a future pytz pin makes this pass on both sides the guard is still correct;
    the test then documents that the divergence closed rather than silently
    dropping the case it was written for.
    """
    from zoneinfo import ZoneInfo

    assert 'America/Coyhaique' not in pytz.all_timezones
    with pytest.raises(pytz.UnknownTimeZoneError):
        pytz.timezone('America/Coyhaique')
    with pytest.raises(ValidationError):
        SyncUserTimeZoneRequest(time_zone='America/Coyhaique')
    try:
        ZoneInfo('America/Coyhaique')
    except Exception:  # host tz database older than tzdata 2025a
        pytest.skip('host tz database has no America/Coyhaique; divergence not observable here')


def test_admission_uses_the_pinned_pytz_version():
    """The admitted set is the pinned authority's, so the pin is load-bearing."""
    assert pytz.__version__ == '2024.1'
    for zone in SCHEDULABLE:
        assert pytz.timezone(zone) is not None


def test_fcm_token_field_is_still_required_and_untouched_by_validation():
    assert SaveFcmTokenRequest(fcm_token='token-abc', time_zone='UTC').fcm_token == 'token-abc'
    with pytest.raises(ValidationError):
        SaveFcmTokenRequest(time_zone='UTC')
