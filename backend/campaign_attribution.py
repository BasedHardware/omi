"""One definition of a push-campaign id, shared by its producer and consumer.

A campaign id travels from the send (`POST /v1/notification`) through the client
tap to the download CTA (`GET /v2/desktop/download/latest`), where it lands on a
space-separated Cloud Logging line. Both ends validate against the rules here:
if the sender accepted an id the download route rejects, the send would look fine
and the CTA would 400, losing exactly the attribution the campaign was set up to
capture.

Deliberately dependency-free so either router can import it without pulling in a
notification or release-pipeline import graph.
"""

# Excludes whitespace so an id cannot forge a field in the log line it lands on.
CAMPAIGN_ID_MAX_LENGTH = 64
CAMPAIGN_ID_PATTERN = r'^[A-Za-z0-9._:-]+$'

# Stands in for "this download carried no campaign". Parentheses sit outside
# CAMPAIGN_ID_PATTERN, so a real campaign cannot collide with the sentinel and be
# silently counted into the untracked bucket.
NO_CAMPAIGN_SENTINEL = '(absent)'
