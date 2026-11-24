# Retire the live capture merge-preservation experiment

The live transcript planner now always uses the existing text repair and manual speaker protections. The retired `LIVE_CAPTURE_WINDOW_MERGE_PRESERVATION` switch had allowed the planner to keep provider pieces separate when their capture windows were disjoint or unknown. The independent [accepted-send window union](../../listen_pusher_pipeline.mdx#receiver-proven-live-merge-unions) continues to use its existing evidence, ordering and replay rules.

On November 22 the switch was false on all five sampled serving backend revisions and all 22 Ready listener and 18 Ready pusher pods. Sampled batch workers had no binding and defaulted to false. The retirement removes the reader and deployment declarations. Existing transcripts and released clients keep their payload format. Rollback is a revert with the switch at its previous off value.

The [off-path parity fixtures](../../../tests/unit/test_live_capture_off_parity.py) and [merge-union tests](../../../tests/unit/test_capture_window_merge_union_r5.py) cover the serving path. Replays for Deepgram, Soniox and Modulate produced identical stored payloads and counter deltas before and after removal.
