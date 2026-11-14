"""Canonical Offline Sync upload names.

Released apps name a same-second WAL collision ``<stem>_<ts>_u<n>.bin`` (the
sequence AFTER the capture time). Every timestamp read takes the trailing
``u<n>`` as the capture time and refuses the file as invalid_capture_time on
every retry, although its clock is sound. An optional ``_clke<run>`` token
(``utils.sync.clock_run``) sits directly before the timestamp.
"""

import re

_TRAILING_COLLISION_SEQUENCE = re.compile(
    r'^(?P<stem>.+?)(?P<run>_clke[0-9a-z]{1,32})?_(?P<ts>[0-9]+(?:\.[0-9]+)?)_(?P<seq>u[0-9]{1,9})\.bin$'
)


def canonical_sync_upload_filenames(filenames: list[str]) -> list[str]:
    """Move a trailing ``_u<n>`` collision sequence ahead of the capture time.

    ``<stem>[_clke<run>]_<ts>_u<n>.bin`` becomes ``<stem>_u<n>[_clke<run>]_<ts>.bin``:
    the timestamp is last again for every parser, the clock-run token still sits
    directly before it, and the sequence keeps same-second siblings distinct.
    The timestamp itself is unchanged, so the capture-time window still applies.
    Every other name is returned as is. If renaming would make two names in the
    request equal, every name is left untouched: staging must never overwrite.
    """
    canonical = []
    for name in filenames:
        match = _TRAILING_COLLISION_SEQUENCE.match(name or '')
        canonical.append(f"{match['stem']}_{match['seq']}{match['run'] or ''}_{match['ts']}.bin" if match else name)
    if len(set(canonical)) != len(set(filenames)):
        return list(filenames)
    return canonical
