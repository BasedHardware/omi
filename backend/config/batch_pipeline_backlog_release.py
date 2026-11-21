"""Pure operator configuration for the fenced backlog authority, never a job policy snapshot.

Reads happen per heartbeat, not at import; invalid or short reach fails closed.
"""

import os
import re
from dataclasses import dataclass

PREFIX = 'BATCH_PIPELINE_BACKLOG_RELEASE_'
MIN_REACH_SECONDS = 30 * 86400
MAX_OWNER_KEYS = 100


def valid_owner_keys(keys: object) -> bool:
    return (
        isinstance(keys, (list, tuple))
        and len(keys) <= MAX_OWNER_KEYS
        and all(isinstance(key, str) and re.fullmatch('[0-9a-f]{64}', key) for key in keys)
        and len(set(keys)) == len(keys)
    )


@dataclass(frozen=True)
class WriterConfig:
    enabled: bool = False
    state: str = 'closed'
    rate_per_hour: int = 0
    reach_seconds: int = 0
    mode: str = 'allowlist_only'
    owner_keys: tuple[str, ...] = ()

    def validate(self):
        if (
            type(self.enabled) is not bool
            or self.state not in ('open', 'closed')
            or self.mode not in ('all', 'allowlist_only')
            or type(self.rate_per_hour) is not int
            or self.rate_per_hour < 0
            or type(self.reach_seconds) is not int
            or (self.reach_seconds != 0 and self.reach_seconds < MIN_REACH_SECONDS)
            or not valid_owner_keys(self.owner_keys)
        ):
            raise ValueError('invalid backlog heartbeat configuration')
        return self

    @classmethod
    def from_env(cls):
        writer = os.getenv('BATCH_PIPELINE_BACKLOG_RELEASE_WRITER', 'disabled').strip().lower()
        if writer not in ('enabled', 'disabled'):
            raise ValueError('backlog writer must be enabled or disabled')
        return cls(
            enabled=writer == 'enabled',
            state=os.getenv('BATCH_PIPELINE_BACKLOG_RELEASE_STATE', 'closed').strip().lower(),
            rate_per_hour=int(os.getenv('BATCH_PIPELINE_BACKLOG_RELEASE_RATE_PER_HOUR', '0')),
            reach_seconds=int(os.getenv('BATCH_PIPELINE_BACKLOG_RELEASE_REACH_SECONDS', '0')),
            mode=os.getenv('BATCH_PIPELINE_BACKLOG_RELEASE_MODE', 'allowlist_only').strip().lower(),
            owner_keys=tuple(
                filter(None, os.getenv('BATCH_PIPELINE_BACKLOG_RELEASE_OWNER_KEYS', '').strip().split(','))
            ),
        ).validate()
