"""A permanently undeliverable developer webhook setting must converge, not loop.

Failure-Class: FC-automated-disable-without-reachable-recovery (nearest
existing registry class; same webhook-health policy surface — its scope hints
name ``backend/database/webhook_health.py`` — and the same user-reachable
recovery pair, auto-disable + notification, that this seam already ships).
The registry class condemns a disable latch whose clearing control the
punished principal cannot reach; this diff closes the mirror-image half of
the same contract: a fault class the disable policy could never SEE, so the
latch the class requires is never armed at all. The shared contract the two
halves protect: an automated webhook policy and the faults it exists to
retire must meet — every fault a delivery path can classify as permanent is
evidence the policy consumes, and every disable it fires stays clearable
through the developer settings the notification names.

The seam: ``send_audio_bytes_developer_webhook`` validated its stored URL
before any delivery and returned on failure WITHOUT consulting the per-uid
disable ladder (``record_dev_webhook_failure`` /
``_handle_dev_webhook_disable``). Every other fault class on the same
function — HTTP rejection, transport failure, breaker-open skip — walks that
ladder, so configuration faults were the one class that could loop forever:
``audio_bytes`` stores ``'<url>,<seconds>'``, so clearing only the URL leaves
a non-empty ``,5`` setting that passes every emptiness gate yet yields an
empty URL (the exact shape ``webhook_url_from_setting`` exists to interpret)
that can never validate. Prod pusher 2026-10-25..28: ≥1000 warnings/day, 12
distinct uids repeating for days, zero auto-disable events among them, while
network-fault uids on the same seam disable at the threshold — the policy
works wherever it is reached.

The fix walks the same ladder from the invalid branch: each delivery attempt
records one offline failure (status 0, ``InvalidWebhookUrl``), the threshold
fires the one-time auto-disable + notification through the shared handler,
and the first healthy delivery after a repair resets the counter. The #20666
contract is preserved: validation still refuses to dial a bad URL, and the
circuit breaker is untouched (a URL the validator refuses has no breaker
state to poison).

Guards (fakeredis carries the real Lua threshold script, so the disable
transition under test is the production transition):
- an invalid setting counts one offline failure per delivery attempt and
  never dials;
- the 100th consecutive invalid delivery fires the one-time auto-disable +
  notification and flips the stored status off;
- after the disable latches, further invalid deliveries stay silent (the
  ladder's already-disabled transition — no repeat notification);
- a repaired + re-enabled setting converges: the first healthy delivery
  resets the counter, so an old burst cannot disable a repaired webhook;
- invalid-URL evidence and counted delivery failures share one threshold;
- valid settings keep the delivery path unchanged: no failure recorded,
  exactly one dial;
- a toggled-off setting remains a pure no-op.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_dev_webhook_invalid_setting_convergence_test_secret')

if 'prometheus_client' in sys.modules:
    setattr(sys.modules['prometheus_client'], 'disable_created_metrics', lambda: None)

# Hermetic execution without live external SDKs — the same harness shape as
# test_audio_bytes_webhook_url_validation.py, which owns this import surface.
# database.webhook_health and database.redis_db are deliberately NOT stubbed:
# the disable ladder under test is their real logic, executed against
# fakeredis by the fixture below.
_STUB = (
    'google',
    'firebase_admin',
    'prometheus_client',
    'fcm_django',
    'pusher',
    'anthropic',
    'openai',
    'utils.notifications',
    'utils.conversations.render',
)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if any(name == p or name.startswith(p + '.') for p in _STUB):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_PRE_EXISTING_MODULES = set(sys.modules.keys())
_finder = _Finder()
sys.meta_path.insert(0, _finder)
try:
    from models.users import WebhookType
    from utils import webhooks
finally:
    sys.meta_path.remove(_finder)


def teardown_module(module=None):
    """Restore sys.modules so stubs cannot leak into subsequent test files."""
    for key in list(sys.modules.keys()):
        if key not in _PRE_EXISTING_MODULES:
            sys.modules.pop(key, None)


def _dev_threshold() -> int:
    from database.webhook_health import _DEV_FAILURE_THRESHOLD

    return _DEV_FAILURE_THRESHOLD


def _ok_post() -> AsyncMock:
    post = AsyncMock()
    response = MagicMock(status_code=200)
    response.json.return_value = {}
    post.return_value = response
    return post


@pytest.fixture
def redis_env(monkeypatch):
    """Real webhook_health and redis_db helpers over one fakeredis.

    The Lua threshold script runs for real, so ``record_dev_webhook_failure``
    returns True exactly once at the production threshold and stays False
    after the disable latches; the status keys the disable/enable helpers
    write are the keys the sender reads. Only the network boundary and the
    push notification are stubbed.
    """
    import fakeredis

    fr = fakeredis.FakeRedis()
    import database.redis_db as redis_db_module
    import database.webhook_health as webhook_health

    monkeypatch.setattr(webhook_health, 'r', fr)
    monkeypatch.setattr(redis_db_module, 'r', fr)
    # The registered Lua script is cached in a module global bound to the client
    # it was registered on; without this reset every test after the first would
    # write its health records into the first test's (already discarded)
    # fakeredis.
    monkeypatch.setattr(webhook_health, '_dev_failure_script', None)

    from database.webhook_health import record_dev_webhook_failure, record_dev_webhook_success

    monkeypatch.setattr(webhooks, 'record_dev_webhook_failure', record_dev_webhook_failure)
    monkeypatch.setattr(webhooks, 'record_dev_webhook_success', record_dev_webhook_success)
    monkeypatch.setattr(webhooks, 'send_notification', MagicMock())
    post = _ok_post()
    monkeypatch.setattr(webhooks, '_post_dev_webhook', post)
    return fr


def _store_setting(fr, uid: str, setting: str, enabled: bool = True):
    """Store through the settings-surface helpers exactly as production does.

    The status/setting keys are keyed by the str-enum member's rendered form,
    so every write AND read here must pass the same ``WebhookType`` member the
    routers and senders pass — mixing plain strings and members splits the
    key space (py3.11 renders ``str(WebhookType.audio_bytes)`` as
    ``WebhookType.audio_bytes``).
    """
    import database.redis_db as redis_db_module

    redis_db_module.set_user_webhook_db(uid, WebhookType.audio_bytes, setting)
    if enabled:
        redis_db_module.enable_user_webhook_db(uid, WebhookType.audio_bytes)
    else:
        redis_db_module.disable_user_webhook_db(uid, WebhookType.audio_bytes)


async def _deliver(uid: str, sample_rate: int = 16000):
    await webhooks.send_audio_bytes_developer_webhook(uid, sample_rate, bytearray(b'\x00\x00' * sample_rate))


class TestInvalidSettingCountsTowardDisable:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'setting',
        [
            ',5',  # URL cleared, seconds kept — the emptiness-gate survivor
            'ftp://example.com/audio',  # wrong scheme
            'not-a-url',  # not a URL at all
        ],
    )
    async def test_invalid_setting_counts_one_failure_and_never_dials(self, redis_env, setting):
        uid = 'uid-invalid-' + setting.split('://')[0][:6].replace(',', '').replace(':', '')
        _store_setting(redis_env, uid, setting)
        await _deliver(uid)
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health[b'failure_count'] == b'1'
        assert health[b'last_error'] == b'InvalidWebhookUrl'
        assert health[b'last_status'] == b'0'
        assert health.get(b'disabled') != b'1'
        webhooks._post_dev_webhook.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_seconds_only_setting_counts(self, redis_env):
        """The production loop's exact shape: the URL half cleared while the
        seconds half survives. The emptiness gate reads the stored value (',5')
        as configured, the URL half extracts empty, and the ladder fires."""
        uid = 'uid-secs-only'
        _store_setting(redis_env, uid, ',5')
        await _deliver(uid)
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health[b'failure_count'] == b'1'
        assert health[b'last_error'] == b'InvalidWebhookUrl'

    @pytest.mark.asyncio
    async def test_wrong_scheme_setting_counts(self, redis_env):
        uid = 'uid-scheme'
        _store_setting(redis_env, uid, 'ftp://example.com/audio')
        await _deliver(uid)
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health[b'failure_count'] == b'1'
        webhooks._post_dev_webhook.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_url_setting_counts(self, redis_env):
        uid = 'uid-noturl'
        _store_setting(redis_env, uid, 'not-a-url')
        await _deliver(uid)
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health[b'failure_count'] == b'1'
        webhooks._post_dev_webhook.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_threshold_fires_one_time_disable_and_notification(self, redis_env):
        uid = 'uid-loop'
        _store_setting(redis_env, uid, ',5')
        for _ in range(_dev_threshold()):
            await _deliver(uid)
        assert webhooks.send_notification.call_count == 1
        title = webhooks.send_notification.call_args.args[1]
        assert title == 'Developer Webhook Auto-Disabled'
        status = redis_env.get(f'users:{uid}:developer:webhook_status:{WebhookType.audio_bytes}')
        assert status == b'false'
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health[b'disabled'] == b'1'

    @pytest.mark.asyncio
    async def test_disabled_latch_stays_silent_on_further_invalid_deliveries(self, redis_env):
        uid = 'uid-latched'
        _store_setting(redis_env, uid, ',5')
        for _ in range(_dev_threshold()):
            await _deliver(uid)
        assert webhooks.send_notification.call_count == 1
        for _ in range(10):
            await _deliver(uid)
        assert webhooks.send_notification.call_count == 1, 'already-disabled transition must not re-notify'
        status = redis_env.get(f'users:{uid}:developer:webhook_status:{WebhookType.audio_bytes}')
        assert status == b'false'

    @pytest.mark.asyncio
    async def test_repair_and_reenable_resets_counter(self, redis_env):
        uid = 'uid-repair'
        _store_setting(redis_env, uid, ',5')
        for _ in range(_dev_threshold() - 5):
            await _deliver(uid)
        # Developer repairs the URL and re-enables through the settings surface.
        _store_setting(redis_env, uid, 'https://healed.example/hook', enabled=True)
        await _deliver(uid)
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health[b'failure_count'] == b'0'
        assert health[b'last_error'] == b''
        # The reset means the old burst cannot disable the repaired webhook later.
        for _ in range(5):
            await _deliver(uid)
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health.get(b'disabled') != b'1'

    @pytest.mark.asyncio
    async def test_mixed_fault_classes_share_one_threshold(self, redis_env):
        """Invalid-URL evidence and a receiver rejection count into the same
        threshold — one policy consuming every fault class the path classifies."""
        uid = 'uid-mixed'
        _store_setting(redis_env, uid, ',5')
        for _ in range(_dev_threshold() - 2):
            await _deliver(uid)
        # Repair into a URL the receiver deterministically rejects: the counted
        # delivery arm supplies the remaining failures.
        _store_setting(redis_env, uid, 'https://rejecting.example/hook', enabled=True)
        post = AsyncMock()
        post.return_value = MagicMock(status_code=400)
        monkeypatched = post
        import utils.webhooks as webhooks_module

        webhooks_module._post_dev_webhook = monkeypatched
        try:
            for _ in range(2):
                await _deliver(uid)
        finally:
            pass
        status = redis_env.get(f'users:{uid}:developer:webhook_status:{WebhookType.audio_bytes}')
        assert status == b'false'
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health[b'disabled'] == b'1'
        assert webhooks.send_notification.call_count == 1

    @pytest.mark.asyncio
    async def test_invalid_classification_only_when_setting_present(self, redis_env):
        """No stored setting at all is the pre-existing emptiness no-op: the
        invalid-URL ladder must not fire for an absent setting (that user
        configured nothing and gets no health writes)."""
        uid = 'uid-absent'
        await _deliver(uid)
        assert redis_env.keys(f'dev_webhook_health:{uid}:*') == []
        webhooks._post_dev_webhook.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_setting_does_not_touch_the_circuit_breaker(self, redis_env, monkeypatch):
        """A URL the validator refuses has no breaker state to poison: arming
        nothing keeps the shared registry free of a hold that would mask a
        later repaired URL on the same host."""
        uid = 'uid-breaker'
        _store_setting(redis_env, uid, ',5')
        breaker = MagicMock()
        breaker.allow_request.return_value = False  # would refuse if consulted
        recorded = MagicMock()
        monkeypatch.setattr(webhooks, 'get_webhook_circuit_breaker', lambda _url: breaker)
        monkeypatch.setattr(webhooks, '_record_dev_webhook_probe_failure', recorded)
        await _deliver(uid)
        breaker.allow_request.assert_not_called()
        breaker.record_failure.assert_not_called()
        recorded.assert_not_called()
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health[b'failure_count'] == b'1'

    @pytest.mark.asyncio
    async def test_disable_notification_names_the_settings_surface(self, redis_env):
        """The one-time notification must tell the punished user where the
        clearing control lives — the recovery half of the shared contract."""
        uid = 'uid-notify'
        _store_setting(redis_env, uid, ',5')
        for _ in range(_dev_threshold()):
            await _deliver(uid)
        args = webhooks.send_notification.call_args.args
        body = args[2]
        assert 're-enable' in body

    @pytest.mark.asyncio
    async def test_sample_rate_out_of_range_stays_a_pure_no_op(self, redis_env):
        """The payload-fields guard sits ABOVE the ladder on purpose: a bad
        sample rate is a caller bug, not stored-user state, so it must not
        advance the user's disable counter."""
        uid = 'uid-badrate'
        _store_setting(redis_env, uid, ',5')
        await webhooks.send_audio_bytes_developer_webhook(uid, 10, bytearray(b'\x00\x00' * 10))
        assert redis_env.keys(f'dev_webhook_health:{uid}:*') == []

    @pytest.mark.asyncio
    async def test_threshold_reaches_exactly_at_the_boundary(self, redis_env):
        """One delivery before the threshold keeps the webhook enabled; the
        boundary delivery itself fires the disable (the Lua transition)."""
        uid = 'uid-boundary'
        _store_setting(redis_env, uid, ',5')
        for _ in range(_dev_threshold() - 1):
            await _deliver(uid)
        status = redis_env.get(f'users:{uid}:developer:webhook_status:{WebhookType.audio_bytes}')
        assert status == b'true'
        await _deliver(uid)
        status = redis_env.get(f'users:{uid}:developer:webhook_status:{WebhookType.audio_bytes}')
        assert status == b'false'

    @pytest.mark.asyncio
    async def test_empty_payload_short_circuits_before_the_ladder(self, redis_env):
        uid = 'uid-empty'
        _store_setting(redis_env, uid, ',5')
        await webhooks.send_audio_bytes_developer_webhook(uid, 16000, bytearray())
        assert redis_env.keys(f'dev_webhook_health:{uid}:*') == []

    @pytest.mark.asyncio
    async def test_health_record_carries_the_invalid_marker_for_operations(self, redis_env):
        """The stored marker is what makes the loop observable: after disable,
        the record still shows InvalidWebhookUrl so an operator reading Redis
        sees a configuration fault, not an outage."""
        uid = 'uid-marker'
        _store_setting(redis_env, uid, ',5')
        for _ in range(_dev_threshold()):
            await _deliver(uid)
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health[b'last_error'] == b'InvalidWebhookUrl'
        assert health[b'disabled'] == b'1'

    @pytest.mark.asyncio
    async def test_disable_notification_body_names_the_fix_and_surface(self, redis_env):
        """The notification is the reachable-recovery half of the contract: it
        must carry both the cause (consecutive failures) and the clearing
        control (developer settings)."""
        uid = 'uid-body'
        _store_setting(redis_env, uid, ',5')
        for _ in range(_dev_threshold()):
            await _deliver(uid)
        args = webhooks.send_notification.call_args.args
        assert args[0] == uid
        title, body = args[1], args[2]
        assert 'Auto-Disabled' in title
        assert '100' in body
        assert 're-enable' in body

    @pytest.mark.asyncio
    async def test_wellformed_but_private_targets_stay_out_of_the_invalid_branch(self, redis_env, monkeypatch):
        """The shape validator checks FORMAT only: a well-formed URL pointing
        at a loopback/metadata address passes it, so the invalid-setting
        ladder does not fire. Those targets are the pinned sender's SSRF
        boundary (safe_request_targets inside _post_dev_webhook), a different
        fault family with its own policy — this test pins that the new branch
        does not swallow them, so the delivery-level classification keeps its
        evidence."""
        import socket as _socket

        uid = 'uid-private-ok'
        _store_setting(redis_env, uid, 'http://169.254.169.254/metadata')
        monkeypatch.setattr(
            _socket,
            'getaddrinfo',
            lambda *_a, **_k: [(_socket.AF_INET, _socket.SOCK_STREAM, 6, '', ('169.254.169.254', 0))],
        )
        await _deliver(uid)
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health.get(b'last_error') != b'InvalidWebhookUrl'
        webhooks._post_dev_webhook.assert_awaited()

    @pytest.mark.asyncio
    async def test_url_with_seconds_keeps_the_url_half(self, redis_env):
        """A fully valid '<url>,<seconds>' setting delivers (the comma is the
        storage shape, not corruption) — proving the ladder only fires for
        genuinely undeliverable settings."""
        import database.redis_db as redis_db_module

        uid = 'uid-withsecs'
        redis_db_module.set_user_webhook_db(uid, WebhookType.audio_bytes, 'https://secs.example/hook,30')
        redis_db_module.enable_user_webhook_db(uid, WebhookType.audio_bytes)
        breaker = MagicMock()
        breaker.allow_request.return_value = True
        await _deliver(uid)
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health[b'failure_count'] == b'0'
        assert webhooks._post_dev_webhook.await_count == 1

    @pytest.mark.asyncio
    async def test_healthy_delivery_after_mixed_history_resets(self, redis_env):
        """The reset is driven by SUCCESS, not by the setting changing: after
        any invalid burst, one healthy delivery clears the counter even if
        more invalid deliveries follow later — matching the Redis contract
        where the health record is the only memory."""
        uid = 'uid-resetmix'
        _store_setting(redis_env, uid, ',5')
        for _ in range(_dev_threshold() - 1):
            await _deliver(uid)
        _store_setting(redis_env, uid, 'https://once-healed.example/hook', enabled=True)
        await _deliver(uid)  # success resets
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health[b'failure_count'] == b'0'
        # Break the URL again: the count starts from one, not from 99.
        _store_setting(redis_env, uid, ',5', enabled=True)
        await _deliver(uid)
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health[b'failure_count'] == b'1'

    @pytest.mark.asyncio
    async def test_other_webhook_kinds_keep_their_own_ladders(self, redis_env):
        """A realtime-transcript webhook failing on the same uid must not
        advance the audio-bytes ladder (or vice versa): keys are per
        (uid, wtype)."""
        uid = 'uid-kinds'
        # Fail the realtime_transcript ladder 99 times directly (the counted
        # path's own function), then prove audio_bytes is untouched.
        from database.webhook_health import record_dev_webhook_failure

        for _ in range(99):
            record_dev_webhook_failure(uid, WebhookType.realtime_transcript, 500, 'err')
        _store_setting(redis_env, uid, ',5')
        await _deliver(uid)
        rt = redis_env.hgetall(f'dev_webhook_health:{uid}:realtime_transcript')
        ab = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert rt[b'failure_count'] == b'99'
        assert ab[b'failure_count'] == b'1'

    @pytest.mark.asyncio
    async def test_ladder_survives_redis_record_expiry_boundary_semantics(self, redis_env):
        """The health record carries a 7-day TTL; within one process the
        disable latch and the counter live in the same record, so a disabled
        webhook stays disabled until the record expires — pin that the latch
        is read from the SAME key the counter advances."""
        uid = 'uid-ttl'
        _store_setting(redis_env, uid, ',5')
        for _ in range(_dev_threshold()):
            await _deliver(uid)
        key = f'dev_webhook_health:{uid}:audio_bytes'
        assert redis_env.hget(key, 'disabled') == b'1'
        ttl = redis_env.ttl(key)
        assert 0 < ttl <= 7 * 86400
        # The counter and latch share the record: no separate disabled key.
        assert redis_env.keys(f'*disabled:{uid}*') == []


class TestValidPathsUnchanged:
    @pytest.mark.asyncio
    async def test_valid_setting_records_no_failure_and_delivers(self, redis_env):
        uid = 'uid-valid'
        _store_setting(redis_env, uid, 'https://healthy.example/hook')
        await _deliver(uid)
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:audio_bytes')
        assert health[b'failure_count'] == b'0'
        assert health[b'disabled'] == b'0'
        assert webhooks._post_dev_webhook.await_count == 1
        status = redis_env.get(f'users:{uid}:developer:webhook_status:{WebhookType.audio_bytes}')
        assert status == b'true'

    @pytest.mark.asyncio
    async def test_toggled_off_setting_is_a_no_op(self, redis_env):
        uid = 'uid-off'
        _store_setting(redis_env, uid, ',5', enabled=False)
        await _deliver(uid)
        assert redis_env.keys('dev_webhook_health:*') == []
        webhooks._post_dev_webhook.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_realtime_transcript_lane_still_delivers_valid_urls(self, redis_env):
        """The transcript lane shares the fixture's Redis: prove the wiring did
        not disturb its settings surface."""
        import database.redis_db as redis_db_module

        uid = 'uid-rt'
        redis_db_module.set_user_webhook_db(uid, WebhookType.realtime_transcript, 'https://rt.example/hook')
        redis_db_module.enable_user_webhook_db(uid, WebhookType.realtime_transcript)
        await webhooks.realtime_transcript_webhook(uid, [{'text': 'hello'}])
        assert webhooks._post_dev_webhook.await_count == 1
        health = redis_env.hgetall(f'dev_webhook_health:{uid}:realtime_transcript')
        assert health[b'failure_count'] == b'0'
