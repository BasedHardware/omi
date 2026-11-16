# Conversations v3: final integration and recovery repairs

Live rows always include nullable finished_at for released Conversation decoders.
Pending/unavailable audio exposes alias status placeholders without URLs; cached
play/export and backup use only the exact dense artifact. Normalized playback
clock defines trims/spans; incomplete pieces cannot cache a partial artifact.

Builder pages retain continuous speech beyond the fixed anchor and use capture
chronology for lookahead. Unreadable transcript markers settle independently.
Processing and privacy-purge sweeps page by cursor and retain per-row retries.
Global open-row validation precedes codec/offload and all transaction batches.

On-open waits at most eight seconds for a shielded tracked reconcile and streams
the stored row on error. Paid work retains its lease until its thread exits;
renewal retries transient faults and stops after fifteen minutes. Expired/token
mismatched writes still fail. Supplied summary leases release on early exits.
Committed terminal-failure transitions have a static-reason counter.

Episode member masks preserve layer visibility; only beta calls refresh the
shared episode/v3 client marker. Layer counts use simple aggregates, or a bounded
10k metadata scan for filtered requests; the index power set is removed.
Backfill stays OFF pending V3-BACKFILL-30D-PARTITIONS before the deletion gate.
No production access, runtime configuration changes or app UI edits.
