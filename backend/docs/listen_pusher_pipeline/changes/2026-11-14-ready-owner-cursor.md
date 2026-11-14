# SCA-2015: ready-owner discovery cursor

The 100-oldest ready page can contain only held backlog and hide a quiet owner's ready fresh row.
Maintenance now visits distinct pending ready owners in owner-key order, persists progress in `{ns}_merge_discovery/cursor`, and resumes after restart.
`BATCH_PIPELINE_READY_DISCOVERY_OWNERS_PER_TICK` overrides the stored budget (default 20, clamped 1..100); each page reads at most that many job rows using seeks past whole owners.
Reads per successful tick = page rows + owners drained × reads per drain + 1 cursor read, plus any empty-seek minimum read charge; discovery writes per tick = 1, in addition to any existing drain writes. The last partial page may include one empty seek.
For a stable owner set, visiting a pass takes `ceil(owners / owners_per_tick) × tick seconds`, plus one empty-page tick to reset the cursor and `pass_started_at` before the next pass.
The cursor visits owners; it does not release held backlog: held rows stay held, and only rows the merge would commit anyway commit. Marker re-offer stays unchanged; cursor read/write/query failures use the old ready page for that tick, and `FailedPrecondition` backs off cursor attempts for 300 seconds per process.
Set `BATCH_PIPELINE_READY_DISCOVERY_CURSOR_ENABLED=false` to restore the 100-oldest ready page exactly; cursor state remains for resumption.
