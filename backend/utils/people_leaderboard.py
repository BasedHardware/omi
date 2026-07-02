"""People-you-talk-to-the-most leaderboard (issue #3808).

Ranks the identified speakers across a set of conversations by how many
conversations the user shared with them and total speaking time. A structured,
non-LLM complement to the yearly Wrapped "top people" analytic. The aggregation is
pure (no I/O) so it is fully unit-tested; the router supplies the conversations and
the person_id -> name map.
"""

from datetime import datetime
from typing import Dict, Iterable, List

from models.other import PersonLeaderboardEntry

# Cap how many conversations one leaderboard request scans, so a heavy account can't
# turn this into an unbounded read.
MAX_LEADERBOARD_CONVERSATIONS = 1000


def build_people_leaderboard(
    conversations: Iterable, names: Dict[str, str], *, limit: int
) -> List[PersonLeaderboardEntry]:
    """Rank people by how much the user talks to them across `conversations`.

    - Each person is counted once per conversation they spoke in (conversation_count).
    - Speaking time is summed from the transcript segments attributed to them.
    - The account owner's own segments (`is_user`) and segments with no `person_id`
      are ignored, so the board is only other people.
    - Names come from `names` (person_id -> display name); unknown ids fall back to
      "Unknown" rather than being dropped.

    Results are ordered most-talked-to first (conversation count, then speaking time),
    with name as a stable tie-breaker, and truncated to `limit`.
    """
    counts: Dict[str, int] = {}
    seconds: Dict[str, float] = {}
    last_talked: Dict[str, datetime] = {}

    for conv in conversations:
        segments = getattr(conv, 'transcript_segments', None) or []
        people_in_conv = set()
        for seg in segments:
            person_id = getattr(seg, 'person_id', None)
            if not person_id or getattr(seg, 'is_user', False):
                continue
            start = getattr(seg, 'start', 0) or 0
            end = getattr(seg, 'end', 0) or 0
            seconds[person_id] = seconds.get(person_id, 0.0) + max(0.0, float(end) - float(start))
            people_in_conv.add(person_id)

        when = getattr(conv, 'created_at', None) or getattr(conv, 'started_at', None)
        for person_id in people_in_conv:
            counts[person_id] = counts.get(person_id, 0) + 1
            if when is not None:
                current = last_talked.get(person_id)
                if current is None or when > current:
                    last_talked[person_id] = when

    entries = [
        PersonLeaderboardEntry(
            person_id=person_id,
            name=names.get(person_id) or 'Unknown',
            conversation_count=count,
            speaking_seconds=round(seconds.get(person_id, 0.0), 1),
            last_talked_at=last_talked.get(person_id),
        )
        for person_id, count in counts.items()
    ]
    entries.sort(key=lambda e: (-e.conversation_count, -e.speaking_seconds, e.name))
    return entries[: max(0, limit)]
