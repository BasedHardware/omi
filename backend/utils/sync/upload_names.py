"""Legacy HTTP upload naming is part of durable sync content identity.

Keep this grammar and the whole-request collision guard stable across rolls:
the content ledger hashes these basenames, not the phone's original names.
"""

import re

_TRAILING_COLLISION_SEQUENCE = re.compile(
    r'^(?P<stem>.+?)(?P<run>_clke[0-9a-z]{1,32})?_(?P<ts>[0-9]+(?:\.[0-9]+)?)_(?P<seq>u[0-9]{1,9})\.bin$'
)


def canonical_sync_upload_filenames(filenames: list[str]) -> list[str]:
    """Use exactly the basename mapping introduced by 7b1a45549b3c.

    Move the sequence before the timestamp, retaining an optional clock run
    directly before that timestamp. Leave the whole request untouched if
    the mapping would collapse two names; HTTP admission must refuse that
    ambiguous request rather than assign a new content identity.
    """
    canonical = []
    for name in filenames:
        match = _TRAILING_COLLISION_SEQUENCE.match(name or '')
        canonical.append(f"{match['stem']}_{match['seq']}{match['run'] or ''}_{match['ts']}.bin" if match else name)
    if len(set(canonical)) != len(set(filenames)):
        return list(filenames)
    return canonical
