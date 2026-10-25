# Explicit speaker tags teach retained voices

A manual tag, pick or confirmation already writes a consent receipt and a
durable speaker-learning job. Person jobs first try the owner-encrypted,
measured Omi-v2 evidence cache; absent/unbound evidence may fall through to
verified audio with the same owner, retention, privacy-generation and deletion
publication fences. A quality/authority rejection cannot bypass those gates
through audio. Automatic and carried labels, rejected/untagged identities and
`use_for_speech_training=false` cannot authorize either path. The verified-audio
fallback retains these privacy gates while the pool's switch is off. Owner
confirmations keep the existing owner path.

`SPEAKER_AUTO_ENROLL_ENABLED` defaults **on**. Set false on API, sync, enrichment,
listen and pusher processes to stop both publication and use of this pool.
Retraction remains active. Restoring true resumes eligible learning on future
explicit jobs; it does not rewrite historical labels or backfill a roster.

Durable vector enrollment requires both the current user's private-cloud sync
retention and `save_other_voice_profiles`, plus a retained source conversation.
This implements lead ruling 65d10d (2026-10-25). Sync-off tags cannot promote
qualfix2's transient encrypted conversation evidence into a durable roster;
that evidence keeps its separate capture/finalization lifetime contract.

The evidence cache gains an additive model marker, binding format v2 and exact segment/acoustic
window bindings. Only freshly embedded or previously bound unchanged entries
receive that authority; older caches abstain. Enrollment selects one acoustic
voice with at least ten seconds of disjoint measured speech, refuses foreign
overlap and inconsistent vectors, and requires a compatible owner vector that
the candidate does not match. Owner exclusion is checked on individual clips,
their normalized average, the full roster average at commit, and the decayed
average when read against the current owner vector. Manual audio voiceprints remain independently
stored and must agree before the vector pool can refresh them.

`people/{person_id}.speaker_auto_enroll_pool` is an AES-GCM ciphertext using
the per-owner key and versioned owner/person AAD. It contains vectors and
source segment IDs only, with no audio, names or transcript. The pool holds
one vote per source conversation, at most five per person, with a 30-day
half-life and 90-day maximum age. Retries preserve the original contribution
age. The shared usable-voiceprint reader computes the live age-weighted vector;
the existing legacy audio enrollment remains available independently.

Publication re-reads the current receipt, transcript, person version, settings,
conversation deletion intent and account/deletion gates inside one Firestore
transaction. A correction retracts intersecting vector contributions in the
same transaction as the new assignment. Conversation deletion fences further
publication and retracts its contributions before hard cleanup. Survivor deletion
also retracts every `sync_merged_from` donor through the bounded owner index,
so a best-effort donor cleanup failure cannot leave a voice contribution behind.
Person/account deletion removes the owning documents. Privacy opt-out removes indexed pools
and updates person versions in the same transaction as the setting change.
Live transcript batches and final match publication re-read derived-profile
authority. The owner stores a bounded per-person SHA-256 token of the encrypted
pool. Publication, source retraction, dismissal and person deletion update that
token atomically with the pool or deletion fence. A stale people snapshot cannot
authorize an older vector against a newer token. Cached vectors also expire at
their earliest contribution's 90-day boundary. Opt-out, privacy-generation change,
owner change, token mismatch or unavailable authority removes cached derived
vectors and their automatic mappings. Sync checks before extraction and again
after embedding IO, immediately before matching publication. Live final authority
checks follow continuity IO. Sync also rechecks immediately before label
application, after any text-detection IO, preserving independent text/manual
authority while removing revoked voice decisions and suggestions. Retraction and deletion fences remain active when
new enrollment is killed off.

All new reads are direct document gets. Bounded content-free person-ID indexes
on the owner (400 maximum) and source conversation (32 maximum) make privacy
and deletion retraction possible without a people scan, new query, queue,
scheduler or index. Reaching either index cap abstains from enrollment.

Verification: `tests/unit/test_speaker_auto_enroll.py` drives real policy and
database functions with strict read-before-write transactions. Durable-job,
publication, privacy, resolution and sync suites cover the surrounding paths.
The Gate T top-N tagging simulation uses local frozen qworker words/turns and
separate enrollment/evaluation audio; it estimates coverage, not production
acceptance. Lead owns merge and deployment; deploy all API/sync/enrichment/listen/
pusher consumers together so privacy retraction and use share this contract.
