"""The pusher runs conversation finalization, so its chart owns the memory fence.

On 2026-08-30 the prod pusher rolled forward from 2026-07-01 and every
conversation stopped finalizing at 15:21:42Z. The pusher chart carries a much
smaller env set than backend-listen, and `MEMORY_ENABLED` was not in it.
`rollout_mode_env_value` fail-closes to `off` when the flag is unset, so
`MemoryService.ensure_canonical_mutation_ready` -- called unconditionally by
`_extract_memories_inner` for every non-discarded conversation -- raised
HTTPException(503). `finalizer.py` logs only `type(error).__name__`, so prod
showed 16k/hour of bare `error=HTTPException` with no status, detail, or
traceback to name the cause.

Presence of the key is not the contract. The contract is that the env the chart
ships must resolve to a mode that permits memory writes, which is what the
finalization path requires to complete.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from config.memory_rollout import MemoryRolloutMode, rollout_mode_env_value

ROOT = Path(__file__).resolve().parents[3]
PUSHER_CHART = ROOT / 'backend' / 'charts' / 'pusher'
LISTEN_CHART = ROOT / 'backend' / 'charts' / 'backend-listen'


def _literal_env(path: Path) -> dict[str, str]:
    loaded = yaml.safe_load(path.read_text(encoding='utf-8'))
    assert isinstance(loaded, dict)
    return {
        str(entry['name']): str(entry['value'])
        for entry in loaded.get('env', [])
        if isinstance(entry, dict) and 'name' in entry and 'value' in entry
    }


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_pusher_env_permits_memory_writes(environment: str) -> None:
    """A pusher that cannot write memories cannot finalize a conversation."""
    env = _literal_env(PUSHER_CHART / f'{environment}_omi_pusher_values.yaml')

    mode = rollout_mode_env_value(env)

    assert mode in {MemoryRolloutMode.write.value, MemoryRolloutMode.read.value}, (
        f'{environment} pusher resolves memory rollout mode to {mode!r}; '
        'ensure_canonical_mutation_ready() raises HTTPException(503) for every '
        'conversation under any other mode'
    )


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_pusher_memory_fence_matches_backend_listen(environment: str) -> None:
    """Both run the same finalization code, so both need the same fence."""
    pusher = _literal_env(PUSHER_CHART / f'{environment}_omi_pusher_values.yaml')
    listen = _literal_env(LISTEN_CHART / f'{environment}_omi_backend_listen_values.yaml')

    assert rollout_mode_env_value(pusher) == rollout_mode_env_value(listen)
