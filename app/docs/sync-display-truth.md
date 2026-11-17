# Pending audio and disconnect display

`WalDerivedViews.pendingWorkAt` owns the pending WAL display inventory. The
standalone `pendingWorkRows` selector applies the same eligibility and device
copy folding for fixtures and the device card. Uploaded handles count until the
later of upload + 24 hours or last confirmed server wait + 5 minutes (inclusive
through the last whole second). The existing `OMI_CATCH_UP_STALE_HANDLE_OFF`
rollback restores legacy expiry behavior; it grants no audio custody rights.

The sheet, banner, On the Way WAL rows and Catching up WAL contribution read this
inventory. On the Way lists server-reported work separately because a server row
can describe the same audio without a WAL identity. Its duration is not added to
WAL day totals. The active banner remembers the audio its run set out to move;
its progress snapshot intentionally holds steady as uploads finish.

Expired handles remain uploaded in the custody ledger. On the Way offers Offline
Sync details under Needs attention, and Offline Sync labels the retained upload
Transcription unavailable. This also covers captures older than the server's
configurable backfill window without guessing that a job was rejected. Display
expiry never changes status, retries, file paths, retention, or deletion rights.
A recent pending response can restore the active display inventory.

Drops are non-manual disconnect rows in the observed seven-day window, including
rows whose reconnect time is still unknown. Only completed non-manual disconnects
contribute reconnect latency. Audio-recovery stamps and failed connect attempts
are different events. UI and diagnostics export use the same drop predicate.
The historical native lifetime counter counts reconnections; the footer now says
reconnections explicitly. Previously missed lifetime reconnects and evicted
history cannot be reconstructed. Both native histories now retain up to 4096 rows
within seven days; extreme event storms can still reach this bounded cap.

Native reconnect history persists the event's timestamp separately from the audio
outage marker. The latter can legitimately predate a disconnect after a process
restart. Connection history survives restart and retires with device-health
identity data. This does not change BLE recovery or audio-outage attribution.

Follow-up: the backend pending-conversation projection has no general capture-age
bound (its optional Home projection uses its own deadlines). Server-only rows can
remain old until their backend owner settles them. This change does not alter
backend projections, read production account data, or establish pendant-device
acceptance.
