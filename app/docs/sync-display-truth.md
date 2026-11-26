# Pending audio and disconnect display

`WalDerivedViews.pendingWorkAt` owns the pending WAL display inventory. The
standalone `pendingWorkRows` selector applies the same eligibility and device
copy folding for fixtures and the device card. Uploaded handles count until the
later of upload + 24 hours or last confirmed server wait + 5 minutes (inclusive
through the last whole second). The existing `OMI_CATCH_UP_STALE_HANDLE_OFF`
rollback restores legacy expiry behavior; it grants no audio custody rights.

The sheet, banner, On the Way WAL rows and Catching up WAL contribution read this
inventory. The owning SyncProvider notifies mounted consumers at the earliest
expiry deadline and cancels that timer on disposal. On the Way lists server-reported work separately because a server row
can describe the same audio without a WAL identity. Its duration is not added to
WAL day totals. The device tile shows the WAL amount while local work exists and
falls back to server-only work only when there is none; server-only work always
keeps its own On the Way section. The active banner remembers the audio its run set out to move;
its progress snapshot intentionally holds steady as uploads finish.

Expired handles remain uploaded in the custody ledger. On the Way offers Offline
Sync details under Needs attention, and Offline Sync labels the retained upload
Transcription unavailable. This also covers captures older than the server's
configurable backfill window without guessing that a job was rejected. Display
expiry never changes status, retries, file paths, retention, or deletion rights.
A recent pending response can restore the active display inventory.
When ready recordings coexist with expired uploads, both Offline Sync banners
keep the ready amount and Sync action; the expired recording retains its
unavailable row and details route.

Drops are non-manual disconnect rows in the observed seven-day window, including
rows whose reconnect time is still unknown. Only completed non-manual disconnects
contribute reconnect latency. Audio-recovery stamps and failed connect attempts
are different events. UI and diagnostics export use the same drop predicate, including when no native
window anchor is available. Lifetime reconnections stay in the separate footer.
When the native anchor is absent, support exports preserve `counters_since` as
null for both counters and count retained rows in the rolling seven-day window.
The historical native lifetime counter counts reconnections; the footer now says
reconnections explicitly. Previously missed lifetime reconnects and evicted
history cannot be reconstructed. Both native histories now retain up to 1024 rows
within seven days; extreme event storms can still reach this bounded cap.

Native reconnect history persists the event's timestamp separately from the audio
outage marker. The latter can legitimately predate a disconnect after a process
restart. Connection history survives restart and retires with device-health
identity data. Persisted connection evidence also participates in existing foreground and
failed-connect retry guards; manual-disconnect and pairing-loss blocks still win.
Audio-outage attribution is unchanged.

Follow-up: the backend pending-conversation projection has no general capture-age
bound (its optional Home projection uses its own deadlines). Server-only rows can
remain old until their backend owner settles them. This change does not alter
backend projections, read production account data, or establish pendant-device
acceptance.

## Review and serialization evidence

The panel review also covers the legacy SyncPage banner, automatic deadline
notifications, absent diagnostics-window anchors, future-row export parity,
stalled-only details reachability, and preservation of retry actions for other
recordings. The render fixtures use a current clock and inject both server
loaders; every capture is synthetic.

The native ring remains bounded, but rewriting a larger retained array has a
cost. [Dated host serialization evidence](evidence/2026-11-17-sync-ring-serialization.json)
records synthetic 500-row and 4096-row cases through the production retention
helper, binary-plist serialization and isolated UserDefaults writes. Reproduce:

```sh
swiftc -parse-as-library app/ios/Runner/Ble/OmiBleEnergyPolicy.swift \
  app/ios/test/ble_history_ring_benchmark.swift -o ./ble-ring-benchmark
./ble-ring-benchmark "$(hostname -s)"
```

This is macOS host evidence; iPhone and Android event-loop latency under a full
ring is not measured. Keep that limitation separate from the passing correctness
checks and the bounded storage representation.

## Offline Sync entry

Device Settings and the device-recording links in On the Way and Activity share
one entry check. A disconnected wearable gets connect guidance. Connected
devices with an unresolved storage check can retry. A readable storage response
enables the existing Sync or Auto Sync route. A completed GATT discovery with
no storage characteristic can identify unsupported hardware.

The device provider shares an in-flight storage check and retires its result on
disconnect, device replacement, or account reset. Phone-local links still open
Offline Sync when unrelated device recordings are waiting.

- Verify connect guidance from Settings and device-recording links with a paired
  CV1 disconnected.
- Verify unresolved, retry, supported and confirmed unsupported states with
  connected-device fixtures.
- Verify phone-local access with pending wearable work and review English and
  German copy alongside the localization consistency check.
