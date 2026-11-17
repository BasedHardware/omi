"""Recording-outcome cohort: count aggregations over finished batch-live rows; no document reads."""

from datetime import datetime, timezone

from google.cloud.firestore_v1.base_query import FieldFilter

LANE_OWNER = 'batch_live_v1'
# The cohort is recordings that finished 45 to 15 minutes before the sample: old
# enough that a healthy pipeline has delivered (transcript p90 is minutes), young
# enough that a cliff shows within half an hour.
COHORT_OLDEST_SECONDS = 2700
COHORT_NEWEST_SECONDS = 900


def recording_outcome_counts(client, now: float) -> tuple[int, int, int]:
    """(finished, transcribed, summarized) over one closed-open ``finished_at`` window.

    The denominator counts finished recordings whether or not any pipeline stage
    saw them, so a stall lowers the shares instead of shrinking the cohort.
    """
    cohort = (
        client.collection_group('conversations')
        .where(filter=FieldFilter('record_lane_owner', '==', LANE_OWNER))
        .where(filter=FieldFilter('status', '==', 'completed'))
        .where(
            filter=FieldFilter('finished_at', '>=', datetime.fromtimestamp(now - COHORT_OLDEST_SECONDS, timezone.utc))
        )
        .where(
            filter=FieldFilter('finished_at', '<', datetime.fromtimestamp(now - COHORT_NEWEST_SECONDS, timezone.utc))
        )
    )
    finished = cohort.count().get(timeout=10, retry=None)[0][0].value
    # The live projection increments the revision in the same write that lands the transcript.
    transcribed = (
        cohort.where(filter=FieldFilter('record_projection_revision', '>', 0)).count().get(timeout=10, retry=None)
    )[0][0].value
    summarized = (
        cohort.where(filter=FieldFilter('summary_output_present', '==', True)).count().get(timeout=10, retry=None)
    )[0][0].value
    return int(finished), int(transcribed), int(summarized)
