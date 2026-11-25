# Keyed from-segments uploads retain their claim on a request budget cut

When synchronous processing of a keyed from-segments upload hits the request
deadline, the route returns the existing retryable 503 with the
`request_budget_exhausted` attribution tag. The lifecycle rolls the stored
claim back to `in_progress`. A retry can atomically re-admit that row and
process the original transcript under the same conversation ID.

The retry receives the usual request budget. If enrichment repeatedly needs
more time than that budget, the row stays available for another retry and
processing can still time out. A provider timeout follows the existing error
and cleanup path.

## Rollout and verification

Pending backend rollout. No flag or migration is required. The idempotency
regression test covers the tagged 503, retained row, successful retry with the
original transcript, and the creation event. After rollout, check for a 200 on
a previously cut upload and track the valid-attempt 503 share in SCA-3846.
