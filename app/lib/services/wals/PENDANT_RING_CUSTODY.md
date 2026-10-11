# Pendant ring custody contract v1 (shared by the firmware PR and the app PR)

**Invariant:** the pendant frees audio from its SD ring only after the app has durably stored it, and
the app says so explicitly. Delivery over Bluetooth is not custody.

This contract is the single source of truth for both PRs. The app PR adds it to the repo at
`app/lib/services/wals/PENDANT_RING_CUSTODY.md`, and the firmware PR links to that path. If either lane
finds the contract wrong or unimplementable, it must stop and report rather than diverge silently. The
supervisor reconciles both PRs.

Ground truth today: `omi/firmware/omi/src/lib/core/storage.c` (commands 0x10–0x13; notifies
0x01–0x05); `sd_card.c` (`advance_read_seq_internal`: a seq below read_seq or above write_seq returns
`-ERANGE`, which surfaces as ack `SEQ_OUT_OF_RANGE` = 10); `app/lib/services/wals/ring_storage_sync.dart`.

## 1. Capability negotiation (backward compatible)

- The `NOTIFY_INFO` (0x02) payload is 31 bytes today: read_seq u64, write_seq u64, capacity u32,
  dropped u64, record_bytes u16, all big-endian.
- v1 firmware appends **byte 31: capability flags (u8)** and **byte 32: contract version (u8, = 1)**,
  (section 1c then appends ring_id, making the payload 41 bytes). Old apps read only the first 31 bytes and are unaffected. New apps treat
  a payload shorter than 41 bytes as `caps = 0` (legacy firmware).
- Flags:
  - `CAP_APP_ACK_RECLAIM = 0x01`: the firmware never advances read_seq on its own. No checkpoint advance
    on BLE send-completion, disconnect or DONE. Only `CMD_RING_ADVANCE` (0x12) or `CMD_RING_CLEAR` (0x13)
    frees ring space. ADVANCE is accepted while a READ transfer is active.
  - `CAP_LIVE_PERSIST = 0x02`: the firmware writes every captured frame to the ring, including while
    live-streaming, and emits live marks (section 3).
  - `CAP_ADVANCE_IDEMPOTENT = 0x04`: ADVANCE with seq ≤ the current read_seq is acked 0 (success, no-op)
    instead of `SEQ_OUT_OF_RANGE`.
  - `CAP_RING_ID = 0x08`: see section 1c.
  - Bits 4–7 are reserved and must be ignored.


## 1b. Opt-in for live persistence (required for old apps)

Old apps never ADVANCE live-persisted data, so new firmware must not persist live audio for them, or
the ring fills and overwrite-oldest discards audio.

- New command **`CMD_CUSTODY_ENABLE = 0x14`**, payload `[0x14, contract_version u8 = 1, requested_caps
  u8]`. The firmware acks with `NOTIFY_ACK` status 0, plus the granted caps where the ack format
  allows; otherwise the app re-reads INFO.
- The app sends it after each connection, once it has read INFO and seen `CAP_LIVE_PERSIST` advertised.
  The firmware enables live persistence **for that connection only**. It reverts to legacy live
  behaviour (no ring write while subscribed) when a new connection has not opted in. While
  disconnected, the firmware writes the ring as it always has.
- `CAP_APP_ACK_RECLAIM` is **not** opt-in: it applies to all apps. Old apps already send ADVANCE after
  DONE (`ring_storage_sync.dart` ~619), so reclaim still happens.
  - Known cost: an old app whose sync is interrupted re-downloads from read_seq on its next sync, which
    can duplicate audio. That's preferred to loss.
  - The firmware PR documents this.
- An unknown opcode on old firmware returns `INVALID_COMMAND` (6). The app treats that as "no custody
  support" and continues in legacy mode.


## 1c. Ring incarnation (amendment, 2026-10-03)

Sequence numbers restart at 0 after CLEAR or metadata reinitialisation (`sd_card.c` `clear_ring_internal`
~550-570, load fallback ~361-367). A persisted `(seq)` alone can therefore free records from a
different ring generation that the phone never received. The fix:

- **`ring_id`:** a random 64-bit identifier stored in ring metadata, generated with the hardware RNG
  (never 0).
  - A new one is generated on every event that resets or invalidates sequence numbers: CLEAR, metadata
    loss or reinitialisation, recovery that cannot prove continuity, card swap/format, factory reset.
  - It never changes otherwise: not on reboot, advance, write or overwrite-oldest.
  - The firmware must never reuse a seq within one `ring_id`.
- **INFO:** v1 firmware appends `ring_id` u64 BE at bytes 33..40, so the payload is **41 bytes**. The
  layout is bytes 0–30 legacy, 31 caps, 32 contract version (=1), 33–40 ring_id. Enlarge the control
  notify buffer, and check the negotiated MTU fits; it already carries 31 bytes.
- **New incarnation-scoped command `CMD_RING_ADVANCE_ID = 0x15`,** payload
  `[0x15, ring_id u64 BE, seq u64 BE]` (17 bytes).
  - If ring_id ≠ current: ack status **`RING_ID_MISMATCH = 11`**, no change.
  - Otherwise: the same semantics as ADVANCE, plus `CAP_ADVANCE_IDEMPOTENT`.
  - Under these caps the app uses **only** 0x15 for advancing. Legacy `0x12` stays for old apps.
  - Advertise it with a new cap bit **`CAP_RING_ID = 0x08`**. All four bits (0x0F) ship together in v1.
- **Live marks carry the ring:** `NOTIFY_LIVE_MARK` (0x06) payload becomes
  `[0x06, ring_id u64, ring_seq u64, live_index u16]`, 19 bytes.
- **App rules:**
  - Persist `(device_id, ring_id, durable_seq)` and live-mark mappings keyed by ring_id.
  - On reconnect, replay or de-duplicate **only if INFO's ring_id equals the persisted one**. Otherwise
    discard the stale checkpoint; never advance on it.
  - Without `CAP_RING_ID`, never replay a persisted ADVANCE across connections. Advance only within the
    connection, after the READ that delivered those records.

## 2. READ / ADVANCE semantics under CAP_APP_ACK_RECLAIM

- The app sends `ADVANCE(seq)` only after every record below `seq` is **durably on phone disk**: written
  and flushed with fsync (`flush: true` or equivalent), with the WAL index entry for that audio persisted.
- The app may advance incrementally during a transfer, after each durably flushed chunk. That bounds the
  sync speed by the phone's flush cadence, not by RAM.
- On reconnect, before a new READ, the app re-sends `ADVANCE(last_durable_seq)` from persisted state, in
  case the previous ADVANCE was lost.
- **Legacy firmware (caps = 0):** the app runs the same code. The firmware already self-freed, so
  ADVANCE may return `SEQ_OUT_OF_RANGE`. The app treats ack 10 on ADVANCE as benign when its seq ≤ the
  firmware's reported read_seq. On legacy firmware the RAM window cannot be closed by the app. The app
  minimizes it with smaller chunks and an fsync before ADVANCE, and records the residual risk in
  telemetry.

## 3. Live persistence under CAP_LIVE_PERSIST

- Live audio packets on the audio characteristic are unchanged (same format, same latency). The ring
  write runs alongside them and never delays the live send.
- The firmware emits **`NOTIFY_LIVE_MARK = 0x06`** on the storage characteristic whenever a ring record
  is committed while a live subscriber is connected (about every 3–4 s at the nominal bitrate). Payload is 19 bytes per section 1c:
  `[0x06, ring_id u64, ring_seq u64, live_index u16]`. Fields:
  - `0x06`;
  - `ring_seq` u64 BE: records < ring_seq are committed to the ring;
  - `live_index` u16 BE: the live audio packet index (the same 16-bit counter carried in the live packet
    header) of the **first frame NOT contained** in records < ring_seq.
- Ordering guarantee: a mark is notified only after every live packet whose frames are in records <
  ring_seq has been queued on the audio characteristic before it, on the same connection. So when the
  app receives the mark, it has already received those live packets, unless the link dropped. Handle
  16-bit wrap relative to the previous mark.
- The app advances to a mark's `ring_seq` only after its live WAL frames up to `live_index` are durably
  flushed. Marks on a connection that dropped before the app's flush are simply not acted on, and those
  records stay in the ring.
- After reconnect, the ring range [read_seq, write_seq) can overlap audio the app already holds from
  live. Duplicate granularity is at most the records after the last advanced mark. The app should drop
  ring-read audio it can prove it already holds durably (by mark mapping). Where it cannot prove it, it
  keeps both copies; losing nothing takes precedence over avoiding duplicates.
- **Ring full:** v1 keeps today's overwrite-oldest policy and keeps counting `dropped` in INFO. Whether
  a full ring should instead stop recording is a product decision for David; neither PR changes it.
  The app surfaces "pendant storage nearly full" from INFO before it fills.

## 4. Out of scope for v1

Server-side "stored" receipts and repair; phone-mic capture; Limitless firmware. The app may still fix
Limitless's app-side ACK ordering (ACK only after fsync). No live packet format change.

## 5. Clarifications from the firmware implementation (draft #20450)

- **Opt-in ACK:** `CMD_CUSTODY_ENABLE` succeeds with `[0x01, 0x00, requested_caps & 0x0F]`. Only bit
  0x02 is a per-connection grant. Connect, disconnect and transport shutdown revoke it. INFO reports
  supported capabilities, not the current grant.
- **`live_index` counts BLE fragments, not Opus frames.** The live audio header is
  `[packet_index u16 LE][fragment_index u8][bytes]`; `packet_index` increments per fragment, and
  `fragment_index` restarts at each frame. A mark's `live_index` is the exclusive next fragment counter
  after the last fragment of the last complete frame in the committed prefix, modulo 65536. The app
  fails closed: no advance on a counter gap, an ambiguous wrap, or a fragmented frame.
- **Marks are suppressed, not continuous.** The firmware emits marks only for a contiguous,
  successfully queued live prefix on the current grant. Offline, unsubscribed, failed-live or dropped
  records break the run, and marks stay suppressed until READ plus a durable ADVANCE covers the earlier
  non-live records. A missing mark means retain and re-download. Do not assume a fixed mark cadence.
- **Uptime-flagged timestamps:** bit 31 (`0x80000000`) of a record timestamp means the low 31 bits are
  seconds since boot (RTC unset), not epoch UTC. The app reads such records as "no usable time".
