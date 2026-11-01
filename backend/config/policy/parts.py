"""Immutable policy parts; the stage owner stamps its part before making decisions."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields
import hashlib
import json
import os
from typing import Self


@dataclass(frozen=True)
class PolicyPart:
    schema_version: int = 1
    source_role: str = 'admission'
    policy_id: str = field(init=False)

    def __post_init__(self):
        content = {f.name: getattr(self, f.name) for f in fields(self) if f.name != 'policy_id'}
        object.__setattr__(
            self,
            'policy_id',
            hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: object) -> Self:
        # Missing additive fields use the original code defaults, never env.
        if not isinstance(raw, Mapping):
            raise ValueError('serialized policy part must be a dict')
        defaults = cls()
        values = {}
        for f in fields(cls):
            if not f.init or f.name not in raw:
                continue
            value, default = raw[f.name], getattr(defaults, f.name)
            if type(value) is type(default) or (type(default) is float and type(value) is int):
                values[f.name] = float(value) if type(default) is float else value
        return cls(**values)


def policy_environment(flags=None):
    return dict(os.environ if flags is None else flags)


def source_role(env, owner: str) -> str:
    return env.get('K_SERVICE') or env.get('OMI_SYNC_STACK_ROLE') or owner


def boolean(env, key, default='false', *, strip=True, uid=None):
    value = env.get(key, default)
    from config.refactor_switches import default_off, default_on

    legacy = (value.strip() if strip else value).lower() == 'true'
    parser = default_on if default == 'true' else default_off
    return parser(key, legacy, uid=uid, environ=env)


def member(uid, env, name, key, *, explicit=False):
    from config.rollout_cohorts import in_rollout_cohort, valid_uid

    members = tuple(value.strip() for value in env.get(key, '').split(',') if value.strip())
    return (valid_uid(uid) and uid in members) if explicit else in_rollout_cohort(uid, name, legacy_members=members)
