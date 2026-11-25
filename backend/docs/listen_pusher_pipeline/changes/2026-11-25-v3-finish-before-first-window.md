# V3 Finish before the first derived window

An empty-body Finish can arrive after Listen closes the capture and before its
first derived window exists. An eligible request with no live window can finish
one recent unclaimed Listen recording. A bounded owner-scoped lookup rejects
ambiguous or protected sources. The cut uses the existing v3 reconcile path.
Server-batch work retains a pending request until transcript or terminal silence
settles the whole recording.

The Finish counter now records the API kill-switch and owner eligibility exits.
See the [v3 pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3).
