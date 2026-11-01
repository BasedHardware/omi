"""One immutable listen decision record, shared by all tasks in a socket.

Only admission resolves. Existing getters use the task-local pin; non-listen
callers retain their original getter semantics. Secrets never enter this record.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, ClassVar
from contextvars import ContextVar
from dataclasses import asdict, dataclass, fields
import math
import json
import os

from config.policy.batch import cohort_bucket
from config.policy.parts import PolicyPart, policy_environment, source_role

if TYPE_CHECKING:
    from config.live_stt_registry import Target

current_listen_policy: ContextVar[ListenSessionPolicy | None] = ContextVar('listen_session_policy', default=None)


@dataclass(frozen=True)
class ListenSessionPolicy(PolicyPart):
    source_role: str = 'listen'
    invalid_fields: tuple[str, ...] = ()
    routing_mode_raw: str = 'off'
    routing_on_percent: float = 0.0
    routing_on: bool = False
    routing_percent_valid: bool = True
    routing_targets_json: str = ''
    routing_disruption_gate: float = 0.08
    routing_redis_timeout_seconds: float = 0.075
    window_allocation_percent: float = 0.0
    window_allocation_valid: bool = True
    window_allocation_parse_valid: bool = True
    window_allocated: bool = False
    # Mirrors stt_provider_policy DEFAULT_MODELS_BY_SURFACE[STREAMING]; Deepgram
    # retired 2026-08-27.
    service_models: tuple[str, ...] = ('modulate-velma-2', 'soniox', 'parakeet')
    failover_recovery_enabled: bool = False
    fallback_liveness_grace_seconds: float = 0.3
    paid_spillover_budget_enabled: bool = False
    paid_spillover_soniox_per_minute: int = 30
    paid_spillover_modulate_per_minute: int = 30
    paid_spillover_deepgram_per_minute: int = 30
    shed_connect_failures: int = 3
    circuit_half_open_probes: int = 1
    account_circuit_cooldown_seconds: float = 1800.0
    no_text_seconds: float = 30.0
    no_text_rescue_enabled: bool = False
    no_text_rescue_seconds: float = 60.0
    learned_language_profile: bool = False
    multi_language_hints: bool = True
    hintable_percent: float = 0.0
    hintable_allocated: bool = False
    demand_enabled: bool = False
    demand_percent: float = 0.0
    demand_admitted: bool = False
    demand_dwell_seconds: float = 15.0

    _targets: ClassVar[tuple[Target, ...] | None] = None

    def __post_init__(self):
        from config.live_stt_registry import parse_registry

        for field in fields(self):
            if field.type in (float, 'float'):
                object.__setattr__(self, field.name, float(getattr(self, field.name)))

        # Parse once, not on every permission/health read. A malformed registry
        # retains the old fail-closed routing path when a consumer asks for it.
        try:
            targets = parse_registry(self.routing_targets_json)
        except (ValueError, TypeError):
            targets = None
        if targets is not None:
            # Record resolved code defaults too: a new pod must not reinterpret
            # an empty env value using a different DEFAULT_TARGETS tuple.
            entries = []
            for target in targets:
                entry = asdict(target)
                if target.replay is None:
                    entry.pop('replay')
                entries.append(entry)
            object.__setattr__(self, 'routing_targets_json', json.dumps(entries, sort_keys=True, separators=(',', ':')))
        object.__setattr__(self, '_targets', targets)
        super().__post_init__()

    @property
    def targets(self):
        if self._targets is None:
            raise ValueError('invalid recorded live STT registry')
        return self._targets

    @property
    def routing_mode(self) -> str:
        value = self.routing_mode_raw.strip().lower()
        return value if value in {'off', 'shadow', 'on'} else 'off'

    @property
    def routing_arm(self) -> str:
        return 'on' if self.routing_on else 'control'

    @property
    def routing_cohort(self) -> str:
        return 'on' if self.routing_on else ('shadow' if self.routing_mode_raw.lower() == 'shadow' else 'off')

    @classmethod
    def from_dict(cls, raw: object) -> ListenSessionPolicy:
        if not isinstance(raw, Mapping) or raw.get('schema_version') != 1:
            raise ValueError('unsupported listen policy schema')
        values = dict(raw)
        models = values.get('service_models')
        if not isinstance(models, (tuple, list)) or any(not isinstance(model, str) for model in models):
            raise ValueError('invalid recorded service models')
        values['service_models'] = tuple(models)
        invalid = values.get('invalid_fields', ())
        if not isinstance(invalid, (tuple, list)) or any(not isinstance(name, str) for name in invalid):
            raise ValueError('invalid recorded listen parse errors')
        values['invalid_fields'] = tuple(invalid)
        defaults = cls()
        # Unknown additive keys are ignored by older readers. Recognized fields
        # are type checked rather than silently replacing a corrupt arm with env.
        for f in fields(cls):
            if f.init and f.name in values:
                value, default = values[f.name], getattr(defaults, f.name)
                if type(default) is float and type(value) in (int, float):
                    values[f.name] = float(value)
                elif type(value) is not type(default):
                    raise ValueError('invalid recorded listen policy field')
        policy = cls(**{f.name: values[f.name] for f in fields(cls) if f.init and f.name in values})
        if raw.get('policy_id') != policy.policy_id:
            raise ValueError('listen policy content hash mismatch')
        return policy


def _number(env, key, default):
    try:
        return float(env.get(key, str(default)))
    except ValueError:
        return float(default)


def _window_percent(env, *, strict=False):
    value = float(env.get('PARAKEET_WINDOW_ALLOCATION_PERCENT', '0'))
    if strict and (not math.isfinite(value) or not 0 <= value <= 100):
        raise ValueError('invalid PARAKEET_WINDOW_ALLOCATION_PERCENT')
    return value if strict else min(100.0, max(0.0, value))


def window_pressure_allocation() -> float:
    """Process-start poller activation retains its original un-clamped input."""
    return float(os.environ.get('PARAKEET_WINDOW_ALLOCATION_PERCENT', '0'))


def window_percent(*, strict=False) -> float:
    policy = current_listen_policy.get()
    if policy is not None:
        if not policy.window_allocation_parse_valid or (strict and not policy.window_allocation_valid):
            raise ValueError('invalid recorded window allocation')
        return policy.window_allocation_percent
    return _window_percent(os.environ, strict=strict)


def window_allocation(uid: str | None) -> bool:
    if not uid:
        return False
    policy = current_listen_policy.get()
    if policy is not None:
        if not policy.window_allocation_parse_valid:
            raise ValueError('invalid recorded window allocation')
        return policy.window_allocated
    return cohort_bucket(uid, 'parakeet-window', bits=64) < window_percent()


def routing_enabled(uid: str | None) -> bool:
    if not uid:
        return False
    policy = current_listen_policy.get()
    if policy is not None:
        if not policy.routing_percent_valid and policy.routing_mode_raw.lower() == 'on':
            raise ValueError('invalid recorded routing percent')
        return policy.routing_on
    env = os.environ
    return (
        env.get('STT_ROUTING_MODE', 'off').lower() == 'on'
        and bool(uid)
        and (cohort_bucket(uid, 'stt-routing-on', bits=64) < _routing_percent(env))
    )


def _routing_percent(env):
    value = float(env.get('STT_ROUTING_ON_PERCENT', '0'))
    if not math.isfinite(value) or not 0 <= value <= 100:
        raise ValueError('invalid STT_ROUTING_ON_PERCENT')
    return value


def routing_targets_json():
    return os.environ.get('STT_ROUTING_TARGETS_JSON', '')


def routing_mode_raw():
    policy = current_listen_policy.get()
    return policy.routing_mode_raw if policy is not None else os.environ.get('STT_ROUTING_MODE', 'off')


def routing_mode():
    value = routing_mode_raw().strip().lower()
    return value if value in {'off', 'shadow', 'on'} else 'off'


def routing_timeout():
    policy = current_listen_policy.get()
    if policy is not None:
        return policy.routing_redis_timeout_seconds
    return min(0.1, max(0.01, _number(os.environ, 'STT_ROUTING_REDIS_TIMEOUT_SECONDS', 0.075)))


def disruption_gate():
    policy = current_listen_policy.get()
    if policy is not None and 'routing_disruption_gate' in policy.invalid_fields:
        raise ValueError('invalid recorded disruption gate')
    value = (
        policy.routing_disruption_gate
        if policy is not None
        else float(os.environ.get('STT_ROUTING_DISRUPTION_GATE', '0.08'))
    )
    if not math.isfinite(value) or not 0 < value < 1:
        raise ValueError('disruption gate must be between 0 and 1')
    return value


def listen_value(field, key, default):
    """Existing non-session callers keep the exact raw getter; sessions use the stamp."""
    policy = current_listen_policy.get()
    if policy is not None:
        if field in policy.invalid_fields:
            raise ValueError('invalid recorded listen knob')
        return getattr(policy, field)
    return os.environ.get(key, default)


def fallback_liveness_grace(default: float) -> float:
    policy = current_listen_policy.get()
    if policy is None:
        return default
    if 'fallback_liveness_grace_seconds' in policy.invalid_fields:
        raise ValueError('invalid recorded fallback liveness grace')
    return policy.fallback_liveness_grace_seconds


def account_circuit_cooldown() -> float:
    return float(listen_value('account_circuit_cooldown_seconds', 'STT_ACCOUNT_CIRCUIT_COOLDOWN_SECONDS', '1800'))


def service_models(default: list[str]) -> list[str]:
    policy = current_listen_policy.get()
    return list(policy.service_models) if policy is not None else default


def hintable_allocation(uid):
    if not uid:
        return False
    policy = current_listen_policy.get()
    if policy is not None:
        return policy.hintable_allocated
    return bool(uid) and cohort_bucket(uid, 'stt-hintable', bits=64) < _hintable_percent(os.environ)


def _hintable_percent(env):
    try:
        return min(100.0, max(0.0, float(env.get('STT_NON_EN_MULTI_PREFER_HINTABLE_PERCENT', '0'))))
    except ValueError:
        return 0.0


def resolve_listen_policy(
    uid: str, *, flags: Mapping[str, str] | None = None, models=None, liveness_grace_seconds=None
) -> ListenSessionPolicy:
    from config.live_demand import resolve_live_demand
    from config.stt_provider_policy import STTServingSurface, default_models_for_surface

    env = policy_environment(flags)
    invalid_fields = []

    def number(key, field, default, *, integer=False):
        try:
            return int(env.get(key, str(default))) if integer else float(env.get(key, str(default)))
        except ValueError:
            invalid_fields.append(field)
            return default

    # Keep invalid numeric parsing at its original use boundary. An unused
    # failover knob must not reject an otherwise healthy session at admission.
    grace = (
        number('STT_FALLBACK_LIVENESS_GRACE_SECONDS', 'fallback_liveness_grace_seconds', 0.3)
        if liveness_grace_seconds is None
        else liveness_grace_seconds
    )
    gate = number('STT_ROUTING_DISRUPTION_GATE', 'routing_disruption_gate', 0.08)
    probes = max(1, number('STT_CIRCUIT_HALF_OPEN_PROBES', 'circuit_half_open_probes', 1, integer=True))
    account_cooldown = number('STT_ACCOUNT_CIRCUIT_COOLDOWN_SECONDS', 'account_circuit_cooldown_seconds', 1800.0)
    no_text = max(1.0, number('STT_NO_TEXT_SECONDS', 'no_text_seconds', 30.0))
    paid_limits = {
        'soniox': int(
            number('STT_PAID_SPILLOVER_SONIOX_PER_MINUTE', 'paid_spillover_soniox_per_minute', 30, integer=True)
        ),
        'modulate': int(
            number('STT_PAID_SPILLOVER_MODULATE_PER_MINUTE', 'paid_spillover_modulate_per_minute', 30, integer=True)
        ),
        'deepgram': int(
            number('STT_PAID_SPILLOVER_DEEPGRAM_PER_MINUTE', 'paid_spillover_deepgram_per_minute', 30, integer=True)
        ),
    }
    mode = env.get('STT_ROUTING_MODE', 'off')
    try:
        percent, percent_valid = _routing_percent(env), True
    except ValueError:
        percent, percent_valid = 0.0, False
    try:
        window, window_parse_valid = _window_percent(env), True
    except ValueError:
        window, window_parse_valid = 0.0, False
    try:
        _window_percent(env, strict=True)
        window_valid = True
    except ValueError:
        window_valid = False
    # Use the existing parser/cache and preserve its allowlist semantics. Explicit
    # flags form a hermetic environment; production uses the live cohort cache.
    demand = resolve_live_demand(flags=env)
    admitted = demand.admits(uid, explicit=flags is not None)
    hintable = _hintable_percent(env)

    def enabled(key, default='false'):
        from config.policy.parts import boolean

        return boolean(env, key, default, strip=False, uid=uid)

    try:
        shed = min(1000, max(1, int(env.get('STT_SHED_CONNECT_FAILURES', '3'))))
    except ValueError:
        shed = 3
    rescue = _number(env, 'STT_NO_TEXT_RESCUE_SECONDS', 60)
    rescue = min(120.0, max(5.0, rescue)) if math.isfinite(rescue) else 60.0
    configured = (
        tuple(models)
        if models is not None
        else tuple(
            env.get('STT_SERVICE_MODELS', ','.join(default_models_for_surface(STTServingSurface.STREAMING))).split(',')
        )
    )
    return ListenSessionPolicy(
        source_role=source_role(env, 'listen'),
        invalid_fields=tuple(invalid_fields),
        routing_mode_raw=mode,
        routing_on_percent=percent,
        routing_percent_valid=percent_valid,
        routing_on=mode.lower() == 'on' and bool(uid) and cohort_bucket(uid, 'stt-routing-on', bits=64) < percent,
        routing_targets_json=env.get('STT_ROUTING_TARGETS_JSON', ''),
        routing_disruption_gate=gate,
        routing_redis_timeout_seconds=min(0.1, max(0.01, _number(env, 'STT_ROUTING_REDIS_TIMEOUT_SECONDS', 0.075))),
        window_allocation_percent=window,
        window_allocation_valid=window_valid,
        window_allocation_parse_valid=window_parse_valid,
        window_allocated=bool(uid) and cohort_bucket(uid, 'parakeet-window', bits=64) < window,
        service_models=configured,
        failover_recovery_enabled=enabled('STT_FAILOVER_RECOVERY_ENABLED'),
        fallback_liveness_grace_seconds=grace,
        paid_spillover_budget_enabled=enabled('STT_PAID_SPILLOVER_BUDGET_ENABLED'),
        paid_spillover_soniox_per_minute=paid_limits['soniox'],
        paid_spillover_modulate_per_minute=paid_limits['modulate'],
        paid_spillover_deepgram_per_minute=paid_limits['deepgram'],
        shed_connect_failures=shed,
        circuit_half_open_probes=int(probes),
        account_circuit_cooldown_seconds=account_cooldown,
        no_text_seconds=no_text,
        no_text_rescue_enabled=enabled('STT_NO_TEXT_RESCUE_ENABLED'),
        no_text_rescue_seconds=rescue,
        learned_language_profile=enabled('STT_LEARNED_LANGUAGE_PROFILE'),
        multi_language_hints=enabled('STT_MULTI_LANGUAGE_HINTS', 'true'),
        hintable_percent=hintable,
        hintable_allocated=bool(uid) and cohort_bucket(uid, 'stt-hintable', bits=64) < hintable,
        demand_enabled=demand.enabled,
        demand_percent=demand.percent,
        demand_admitted=admitted,
        demand_dwell_seconds=demand.dwell_seconds,
    )


def listen_generation_violations(policy_or_values: ListenSessionPolicy | Mapping[str, Any]) -> tuple[str, ...]:
    """Return impossible resolved listen combinations for policy generation.

    Resolver error states remain representable on ``ListenSessionPolicy`` for
    fail-closed runtime handling. This narrower contract describes valid
    generated policies and sits beside the type so its dependencies stay local.
    """

    def get(key: str) -> Any:
        if isinstance(policy_or_values, Mapping):
            return policy_or_values[key]
        return getattr(policy_or_values, key)

    def has(*keys: str) -> bool:
        return not isinstance(policy_or_values, Mapping) or all(key in policy_or_values for key in keys)

    violations: list[str] = []

    if (
        has('routing_on_percent', 'routing_percent_valid')
        and bool(get('routing_percent_valid'))
        and (not math.isfinite(float(get('routing_on_percent'))) or not 0 <= float(get('routing_on_percent')) <= 100)
    ):
        violations.append('valid_routing_percent_must_be_between_zero_and_one_hundred')
    if (
        has('routing_on_percent', 'routing_percent_valid')
        and not bool(get('routing_percent_valid'))
        and float(get('routing_on_percent')) != 0
    ):
        violations.append('invalid_routing_percent_fails_closed')
    if (
        has('routing_on', 'routing_mode_raw', 'routing_percent_valid', 'routing_on_percent')
        and bool(get('routing_on'))
        and (
            str(get('routing_mode_raw')).strip().lower() != 'on'
            or not bool(get('routing_percent_valid'))
            or float(get('routing_on_percent')) <= 0
        )
    ):
        violations.append('routing_on_requires_on_mode_and_positive_valid_percent')
    if (
        has('routing_mode_raw', 'routing_on')
        and str(get('routing_mode_raw')).strip().lower() != 'on'
        and bool(get('routing_on'))
    ):
        violations.append('routing_off_or_shadow_cannot_select_on_arm')

    if (
        has('window_allocation_percent', 'window_allocation_parse_valid')
        and bool(get('window_allocation_parse_valid'))
        and (
            not math.isfinite(float(get('window_allocation_percent')))
            or not 0 <= float(get('window_allocation_percent')) <= 100
        )
    ):
        violations.append('parsed_window_percent_must_be_clamped')
    if (
        has('window_allocation_parse_valid', 'window_allocation_percent', 'window_allocation_valid', 'window_allocated')
        and not bool(get('window_allocation_parse_valid'))
        and (
            float(get('window_allocation_percent')) != 0
            or bool(get('window_allocation_valid'))
            or bool(get('window_allocated'))
        )
    ):
        violations.append('unparsed_window_percent_fails_closed')
    if (
        has('window_allocated', 'window_allocation_parse_valid', 'window_allocation_percent')
        and bool(get('window_allocated'))
        and (not bool(get('window_allocation_parse_valid')) or float(get('window_allocation_percent')) <= 0)
    ):
        violations.append('window_allocation_requires_positive_parsed_percent')

    if has('hintable_percent') and (
        not math.isfinite(float(get('hintable_percent'))) or not 0 <= float(get('hintable_percent')) <= 100
    ):
        violations.append('hintable_percent_must_be_clamped')
    if (
        has('hintable_allocated', 'hintable_percent')
        and bool(get('hintable_allocated'))
        and float(get('hintable_percent')) <= 0
    ):
        violations.append('hintable_allocation_requires_positive_percent')

    if has('demand_percent') and (
        not math.isfinite(float(get('demand_percent'))) or not 0 <= float(get('demand_percent')) <= 100
    ):
        violations.append('demand_percent_must_be_between_zero_and_one_hundred')
    if has('demand_dwell_seconds') and (
        not math.isfinite(float(get('demand_dwell_seconds'))) or not 5 <= float(get('demand_dwell_seconds')) <= 300
    ):
        violations.append('demand_dwell_must_be_between_five_and_three_hundred_seconds')
    if has('demand_admitted', 'demand_enabled') and bool(get('demand_admitted')) and not bool(get('demand_enabled')):
        violations.append('demand_admission_requires_enabled_demand')

    if (
        has('no_text_rescue_enabled', 'no_text_rescue_seconds')
        and bool(get('no_text_rescue_enabled'))
        and not 5 <= float(get('no_text_rescue_seconds')) <= 120
    ):
        violations.append('no_text_rescue_seconds_must_be_clamped')
    if has('no_text_seconds') and float(get('no_text_seconds')) < 1:
        violations.append('no_text_seconds_must_be_at_least_one')
    if has('shed_connect_failures') and (
        int(get('shed_connect_failures')) < 1 or int(get('shed_connect_failures')) > 1000
    ):
        violations.append('shed_connect_failures_must_be_bounded')
    if has('circuit_half_open_probes') and int(get('circuit_half_open_probes')) < 1:
        violations.append('circuit_half_open_probes_must_be_positive')
    return tuple(violations)
