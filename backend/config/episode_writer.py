"""Pure episode writer settings; read mutable configuration at the call boundary."""

import os
from dataclasses import dataclass

EFFORTS = ('default', 'high', 'xhigh')
SELECTIONS = ('compact', 'deterministic', 'model')


@dataclass(frozen=True)
class EpisodeWriterSettings:
    effort: str = 'default'
    selection: str = 'deterministic'
    claims: bool = False
    selection_effort: str = 'low'
    selection_timeout: float = 30


def episode_writer_settings() -> EpisodeWriterSettings:
    effort = os.getenv('MEETING_NOTES_EPISODE_EFFORT', 'default')
    selection = os.getenv('MEETING_NOTES_EPISODE_SELECTION', 'deterministic')
    selection_effort = os.getenv('MEETING_NOTES_EPISODE_SELECTION_EFFORT', 'low')
    try:
        selection_timeout = float(os.getenv('MEETING_NOTES_EPISODE_SELECTION_TIMEOUT_SECONDS', '30'))
    except ValueError:
        selection_timeout = 30
    if not 1 <= selection_timeout <= 30:
        selection_timeout = 30
    return EpisodeWriterSettings(
        effort=effort if effort in EFFORTS else 'default',
        selection=selection if selection in SELECTIONS else 'deterministic',
        selection_effort=selection_effort if selection_effort in ('low', *EFFORTS) else 'low',
        selection_timeout=selection_timeout,
        claims=os.getenv('MEETING_NOTES_EPISODE_CLAIMS_ENABLED', 'false').strip().lower() in {'true', '1', 'yes'},
    )
