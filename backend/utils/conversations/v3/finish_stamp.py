"""The live-window Finish stamp's field, paths and age limit.

Dependency-free on purpose: ``utils.conversations.v3.metrics`` reads ``FINISH_STAMP_PATHS`` and is reachable from the
GPU batch worker, so it must not import ``live`` (whose config import reaches Cloud Tasks).
"""

from datetime import timedelta

# A live-window Finish stamps its request time and path (``FINISH_STAMP_PATHS``) on its response target's source
# with the first write it stores there. The planner carries the stamp to the derived row that shows that source, and
# that row's first manual-end settlement observes ``FINISH_TO_VISIBLE`` once. Older than ``FINISH_STAMP_MAX_AGE``, the
# stamp is dropped instead of observed.
FINISH_STAMP_FIELD = 'v3_finish_requested'
FINISH_STAMP_PATHS = ('tail', 'newer', 'newer_dual')
FINISH_STAMP_MAX_AGE = timedelta(hours=2)
