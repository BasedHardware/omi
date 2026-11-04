# Episode attach read reduction

Sync attach retains the recorded-time ownership and recovery contract in
[the pipeline guide](../../listen_pusher_pipeline.mdx). Automatic recorded
windows now skip repartition only when an exact recorded start/end/source,
member list and owner state revision match the last canonical partition,
under the timeline fence transaction. Unrelated windows do not invalidate the proof. The current conversation must still exist, be visible,
and point back to that owner. Missing proof or changed evidence falls through.
Recovery still runs so new words within an unchanged span reach notes.

Canonical and fixed-boundary attachment share a transaction read phase and
reuse covered candidate queries only within that attempt. CAS window checks
reuse their existing fence read. Recovery reads each receipt namespace once per
walk and advances its local consumed sets only after a successful CAS; an
unexpected owner revision forces a refresh. Content-only receipts remain valid
when the legacy receipt base is absent. No rollout flag or public API changes.

After deployment, compare `avo/firestore-reads/measure.py` caller rows for
`episode_timeline:recorded_candidates`, `episodes:read_memberships`,
`episode_recorded_components:commit`, and `episode_receipts:get_consumed_ids`
at comparable sync volume. The handoff estimates $15–25/day net, equivalent to
about 28–46 million reads/day at $0.06/100k with the 0.9 net multiplier.
