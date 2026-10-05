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


def episode_writer_settings() -> EpisodeWriterSettings:
    effort = os.getenv('MEETING_NOTES_EPISODE_EFFORT', 'default')
    selection = os.getenv('MEETING_NOTES_EPISODE_SELECTION', 'deterministic')
    return EpisodeWriterSettings(
        effort=effort if effort in EFFORTS else 'default',
        selection=selection if selection in SELECTIONS else 'deterministic',
        claims=os.getenv('MEETING_NOTES_EPISODE_CLAIMS_ENABLED', 'false').strip().lower() in {'true', '1', 'yes'},
    )
