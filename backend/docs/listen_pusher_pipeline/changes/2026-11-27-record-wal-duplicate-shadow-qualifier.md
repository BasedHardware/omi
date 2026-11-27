# Native WAL duplicate shadow reaches proof comparison

SCA-3376 phase 2a. The pre-fence duplicate shadow
([settlement note](2026-11-23-record-wal-duplicate-settlement.md)) ran its
window without one proof comparison. This is a shadow-only fix. Settlement
stays fenced, replies are unchanged, and there is no new config.

## What changed

- **Current app WAL names now parse on the shadow and sampler path.** The
  shared `utils.other.raw_audio.filename_provenance` reads fixed token
  positions. It refuses the names the shipped app writes:
  `audio_<dev>_opus_fs320_16000_1_fs320[_clke<run>]_<ts>.bin`
  (`bt_device.dart` `mapCodecToName`, `wal.dart` `getFileNameByTimeStarts`).
  No such file produced a duplicate descriptor, so `evaluate` returned before
  any ledger or archive read.
  `record_wal_sample.staged_name_provenance` uses the shared parser first and
  keeps its exact fields. A name the shared parser refuses is then matched
  against the app's upload grammar (`orphan_audio_classifier.dart`):
  - the `opus_fs160` or `opus_fs320` codec, whose frame must equal `fs<frame>`;
  - `_clke<run>` directly before the timestamp;
  - the `_u<n>` collision nonces;
  - the Limitless `_r<n>_<seq>` token.

  Anything else stays unparsed. `read_staged_packets`, the only consumer,
  serves both the duplicate shadow and the Nov 24 alignment sampler. The
  shared parser and its storage, handoff and no-speech-coverage callers are
  unchanged (TODO SCA-3376).
- **Attest refusals are counted.**
  `omi_record_wal_handoff_source_attest_refusals_total{reason}` counts each
  native intake that `record_wal_source.attest` admits without a source
  attestation. The reasons are a fixed set of 12, with no ids, and the first
  failing check wins: `not_closed`, `partial`, `upload_failed`,
  `handoff_present`, `unit_count`, `slice_count`, `bucket`, `path`, `format`,
  `clock_source`, `geometry` and `generation`. Every child is exported at zero
  from import.

  The counter adds no reads or writes, and attest's return values are
  unchanged. The `record_wal_handoff_` prefix keeps the series inside the
  existing keep rule of `backend/deploy/cloud_run_gmp_sync.yaml`. That rule
  covers `backend-integration`, which runs record admission, and the
  projection-pump profile.
- **Jobs-missing refusals no longer claim a shadow slot.** The shadow
  previously ran for any 503 without a prior receipt. It now also requires
  the record's jobs, as settle already does (`not prior and jobs and ...`).
  A `record_jobs_missing` refusal has no admitted intake to prove against.
  It could only consume the window's single durable 30 s slot, and its row
  fails `_authority`.

## Cost

Shadow per-claim bounds are unchanged: 104 Firestore point reads, 20 GCS
requests and 16 MiB of manifest bodies. The window bounds are also unchanged:
49,920 point reads, 9,600 GCS RPCs and 7.5 GiB. Claims now reach the bounded
ledger and archive reads instead of returning at the descriptor check. Before
this change those reads were near zero. Parsing reads only the already-staged
local upload.

The sampler likewise now measures current-name files instead of counting them
as unknown duration. That adds local packet parsing and no remote reads.

## Rollout and proof

Kill switch: unset `RECORD_WAL_DUPLICATE_SHADOW_PRE_FENCE` (and the epoch) on
backend-sync. The next approved shadow window proves the fix when it shows
`omi_record_wal_handoff_duplicate_io_total{mode="shadow",unit="gcs_requests"} > 0`
and `omi_record_wal_handoff_duplicate_shadow_checks_total > 0`. Read the attest
refusal reasons from `backend-integration` to size the attestation gap
(0 of 47 sampled prod intakes carried one).
