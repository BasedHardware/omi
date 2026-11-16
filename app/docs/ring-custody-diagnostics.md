# Ring custody export

Settings → device → Diagnostics → Share keeps its existing JSON bundle and adds
`ring_custody` schema 1. No new screen, action, string, account request or upload.
The section is a read-only observation, never custody authority.

At export the app uses the existing connection (`connectionFor`, not connect or
ensureConnection). It reads RTC characteristic 19b10032 as uint32 little-endian
seconds, reads ring status and requests INFO; it never writes 19b10031, reads
record bodies, validates proof files, or issues ADVANCE/DELETE. RTC request and
completion phone timestamps bound transport latency. Epoch/link changes discard
cross-connection readings. Absent/legacy/unreadable state is null with a bounded
reason. There is no clock sync performed by this export.

The flight recorder is process-local and bounded to four devices, 20 events,
16 prefixes from the latest READ, 64 implausible prefixes retained up to 24 hours,
and 60 route-count minute buckets. Restart removes observations; JSON explicitly
reports the collection scope and start. It does not claim 24-hour completeness.
Only eight prefix bytes are retained (timestamp and length/codec prefix), never
an audio frame/body, transcript, title, path, owner or filename. Numeric ordinals,
frame counts, decoded time and adjacent-record plausibility help distinguish
stored timestamps from misframing. End-of-read neighbours remain null.

The getter `PendantRingCustody.diagnosticsByDevice` copies numeric metadata only.
Live-mark observation uses the separate `diagnosticMarkStateByDevice` getter,
whose work is independent of ledger size; it never sorts historical ranges.
The ledger summary uses the union of previously recorded proof ranges; export
never revalidates files or authorizes reclaim. First gap is [frontier, next proof
start), capped at current write_seq. `records_held_behind_gap` counts the suffix
after that gap (including any later gaps), not proof of that suffix's durability.
Batch proof-range count is derived internally from reference type/name prefix;
no names are exported.

Ordinary route counts are accepted LocalWalSync frames, and proof frame counts
are observed publication calls; neither means server acceptance. Batch ingress
and publication require the Q12-AA-owned observation hooks into the same typed
recorder API. Missing batch counters are explicitly unknown, never zero. READ
request/BEGIN/DONE/STOP and ADVANCE attempts/results are observed in the connector;
STOP means incomplete/stopped, not necessarily a timeout. Actual TimeoutException
reports project only its bounded reason and decoded-record count. Precise idle
reason observation may be supplied by Q12-AA's owned loop. Mark outcomes are
inferred from the custody manager's read-only before/after state, with duplicates
reported separately. Nothing changes mark acceptance.

Rollback: revert the diagnostics commit. This removes only observations/export;
it does not alter files, clocks, identities, proof validation or device progress.

The same section includes `local_recording_inventory`. It snapshots active,
retired and foreign memory metadata, then reads main/backup/quarantine/temp JSON,
batch journals, ownership receipt counts, legacy pending-file/job preferences and
recorded boot quarantine/recovery results. It never calls a loader, migration,
recovery, owner resolver, saver or intake. Preference reads bypass validating
getters that can quarantine. File metadata and JSON bytes are read asynchronously
without acquiring the WAL save/custody locks; JSON parsing and correlation use
`offUiIsolate` (the 16,000-row fixture asserts no inline fallback).

Directory totals cover generated `audio_*` bin/part/torn/WAV files. All regular
files are statted so a referenced historical filename outside that pattern is
not falsely called missing. No audio bytes are read. References are the union
of readable indexes/journals/legacy lists and memory snapshots, including backups;
bucket row/audio totals can overlap and are not unique-audio totals. Unreadable
or concurrently changed metadata makes orphan certainty false. The census is a
best-effort observation while capture/uploads can continue, not an atomic backup
or a reindex operation. Disk birth/creation times are not recorded by the WAL
schema or available in portable Dart FileStat, so creation fields are explicitly
null; modification and metadata-change times are labelled separately. No IDs,
paths, filenames, raw index rows or owner values enter the JSON. Known schema
buckets share one physical index; foreign/current/legacy/unstamped owner counts
are categorical only, not per-account identifiers.
