# v3 reconcile task deadline (SCA-2918)

The [reconcile task](../../listen_pusher_pipeline.mdx#conversations-v3-reconcile-task-deadline)
checks one monotonic budget before starting another paid outline, live title,
finalization, integration delivery, or recursive pass. Existing lease cleanup
runs on yield. Completed outlines stay in the fenced cache. Source projection,
finalization, and integration delivery resume from the existing durable markers.

The reserves are 75 seconds for outlines (60-second stream deadline plus 15),
30 for live titles (15-second provider timeout plus 15), 240 for finalization
(120-second notes agent, 90-second v3 notes fallback call, and 30 seconds for
other work and settlement), 75 for delivery (two 30-second webhook waves and
15 seconds for bookkeeping), and 75 for recursion (room for an outline).
These are admission estimates. An already started unit, including all writes
and cleanup, can exceed its reserve. The default 480-second budget leaves
120 seconds before the Cloud Run deadline.

The `omi_conversations_v3_reconcile_budget_yields_total` counter records the
boundary that declined admission. Trace-linked start and duration logs show
which outline, title, finalization, delivery, or commit stage was in flight.
Roll back with `CONVERSATIONS_V3_RECONCILE_DEADLINE=off`.
