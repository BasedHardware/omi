# Script-aware v3 late-rewrite counts

Late summary rewrites count both transcript snapshots using the same
script-aware policy as automatic processing. The existing growth, age and
one-rewrite limits still apply. Offline v3 replay uses the same count for
partial arrivals, final arrivals and replay reports.

The calculation uses already-loaded segment text. Newly eligible rewrites
use normal summary processing. Revert the PR to roll back.

After the serving SHA is verified, compare the rate of
`omi_conversations_v3_summary_writes_total{kind="rewrite"}` and summary
processing errors per attempt with a comparable pre-deploy window. Record
both window boundaries, attempt counts and error counts.
