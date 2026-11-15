# Device capture-clock admission

Ring, LittleFS and Dart Limitless flash importers use the same inclusive UTC
window: 2024-01-01 through phone now +24h. A positive value outside it is
handled like unset RTC, rather than naming a phone WAL under an impossible
calendar date. Legacy SD already applies this window to LIST/marker values.
The build-time rollback is `--dart-define=OMI_DEVICE_CAPTURE_CLOCK_REPAIR_OFF=true`;
absent/false enables the guard. OFF restores the previous importer predicates
and collision naming without rewriting any saved file or index entry.

A phone below the 2024 floor or outside the pendant's signed-31-bit UTC domain
cannot supply an estimate. Positive device stamps retain previous behavior
when that reference is unavailable. This cannot detect a phone that is wrong
but still inside the clock domain; it is not a trusted network-time check.

LittleFS uses the fully decoded file's frame duration and one clock-run token
per file. Ring keeps the existing unread-duration estimate and advances it by
decoded frames in ring order. Invalid values never become calendar anchors;
raw clock jumps/resets conservatively split estimated runs. If an underestimated
unread duration eventually puts an estimated ring start outside the window,
stop without admitting/reclaiming the unproven records. This is estimated
chronology, not reconstruction of capture time. Dart Limitless batches use
their decoded frame duration, with one token per estimated batch.

The upload filename contract is `_clke<run>_<timestamp>.bin`, with a lowercase
alphanumeric nonce of at most 32 characters. Collision `_uN` tokens precede
`clke`, never separate it from the trailing timestamp. Limitless preserves its
existing millisecond filename unit. Device/ring identity, sequence ordinals,
source frames, byte serialization and index-before-ADVANCE are unchanged.
No time estimate authorizes deduplication or a custody acknowledgment.

Existing unmarked files remain byte/name/time identical. The quality-push server
recovery admits those original files with immutable independent receive anchors
and untrusted chronology. Local mtime/creation time only bounds import; it cannot
establish capture order or a shared clock run. There is no local timestamp
migration, synthetic Date estimated label, or migration completion marker.

A plausible timestamp is not proof of record/audio integrity. The 3.0.24 raw
batch body and DATA stream lack end-to-end checksums/offsets. Synthetic probes
show that a valid header with a corrupt body can be read, and balanced wire
loss/extra bytes can satisfy DONE totals. Those separate integrity gaps are
not established as this owner's timestamp generator; the random-byte hypothesis
was withdrawn after his timestamp distribution became available. Broad firmware
rollout remains held for the unresolved generator and measured transfer/reclaim
issues. Q12-AF owns firmware diagnosis and hardening. The first rejected ring
epoch/ordinal is retained in local warning diagnostics. Backend recovery cannot
reconstruct corrupt/missing audio samples.

Native Limitless Transcribe Later has separate Swift/Kotlin writers, outside
these Dart importers; their 2020-only lower bound has no upper-time check. It is
not the CV1 ring path. Those native producers need a separately qualified guard
and clock-token/config propagation; this change does not claim to protect them.
Phone microphone, Watch and live phone safety copies originate on the phone
clock, not these device timestamp fields.

Guards: `test/unit/device_capture_clock_test.dart`,
`ring_storage_sync_no_advance_test.dart`, and
`legacy_storage_limitless_seam_test.dart`, with the same suite also run using
the OFF dart-define. No UI widget/string changes are part of this fix.
