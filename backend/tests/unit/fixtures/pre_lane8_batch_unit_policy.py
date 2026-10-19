"""Admission policy shape frozen from main 4f43b2d7 (E1, the prod reader before #22536).

Rollback fixture: the reader a revert would run must ignore the STT route fields
#22536 adds and recompute the same policy_id for a row it stamped itself.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, fields
import hashlib
import json
import math
from typing import Self


@dataclass(frozen=True)
class PrePolicyPart:
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


@dataclass(frozen=True)
class PreLane8BatchUnitPolicy(PrePolicyPart):
    schema_version: int = 1
    batch_enabled: bool = False
    batch_percent: float = 0.0
    batch_allowlisted: bool = False
    live_admission_enabled: bool = False
    live_record_enabled: bool = False
    retire_percent: float = 0.0
    live_stt_retired: bool = False
    final_pass_enabled: bool = False
    final_pass_authoritative: bool = False

    def __post_init__(self):
        object.__setattr__(self, 'batch_percent', float(self.batch_percent))
        object.__setattr__(self, 'retire_percent', float(self.retire_percent))
        if self.live_stt_retired and not self.batch_enabled:
            raise ValueError('live STT retirement requires batch coverage')
        if not 0 <= self.retire_percent <= self.batch_percent <= 100:
            raise ValueError('retire percent must be nested within batch percent')
        super().__post_init__()

    @classmethod
    def from_dict(cls, raw: object) -> 'PreLane8BatchUnitPolicy':
        if not isinstance(raw, Mapping):
            raise ValueError('serialized admission policy must be a dict')
        values = dict(raw)
        values['batch_percent'] = parse_percent(str(values.get('batch_percent', 0)))
        values['retire_percent'] = min(parse_percent(str(values.get('retire_percent', 0))), values['batch_percent'])
        if not values.get('batch_enabled', False):
            values['live_stt_retired'] = False
        return super().from_dict(values)


def parse_percent(raw: str) -> float:
    try:
        value = float(raw)
        return value if math.isfinite(value) and 0 <= value <= 100 else 0.0
    except (ValueError, TypeError):
        return 0.0
