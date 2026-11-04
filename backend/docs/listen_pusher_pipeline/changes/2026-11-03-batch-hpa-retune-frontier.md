# Batch worker HPA retune after the max-of-two regression

The replacement retune uses ready41/chain0.56, preserving min4/max16 and the
1800s, one-pod/600s stockout policy. #24481's 40/0.6 shape starved 35 minutes in
the existing 24h replay and was reverted in #24493 before any cluster apply.
The existing replay files are unchanged; new sensitivity tests pin the current
and modeled full-volume results. The numerical lower-window frontier is not
qualified for stockouts, and full-volume zero-hot operation cannot fit max16.

See [the scaler contract](../../batch-pipeline-worker.md#capacity-and-autoscaling) and the
[frontier/apply/rollback report](../../batch-pipeline-hpa-frontier.md). Defaults
ship on through the existing production HPA; restore targets 32/0.5 as the kill
switch. No new environment name, pipeline behavior, adapter, worker process
count, or rollout was added. The lead must apply only at current volume and
watch one shed cycle plus 24h before deciding further capacity/traffic changes.
