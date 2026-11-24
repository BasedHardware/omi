# ADR-0008: Private recurring voices from batch finalization

- Status: Accepted
- Date: 2026-11-03
- Deciders: David (binding rulings in the recurring-voice implementation request)
- Owner: speaker rollout lead
- Review by: 2026-11-17

Identity is automatic and inferred, with precision first and no enrollment opt-in.
Confident whole-conversation clusters may teach private, per-user profiles. An
unconfirmed profile never receives a name or creates a person. Only a manual
assignment may bind it to an existing person. The learning lane is batch
finalization; live and sync print loading never reads this roster, and there is
no streaming GPU work or retroactive refresh of past conversations.
Follow-up: bounded identity-only retro-refresh of contributor conversations after confirmation.

Existing retention consent (`private_cloud_sync_enabled` and
`save_other_voice_profiles`) gates reads and writes. Profiles are AES-GCM sealed
using a per-user key and AAD binding user and voice IDs. The user document holds
ciphertext hashes as authority. Authentication, malformed data, unavailable
consent and concurrent deletion all deny publication. Transactions revalidate
the source, consent generation, account fence and person roster generation.
Recurring learning requires a complete voiceprint read; owner, entitlement or
person-roster read failures abort the pass before inference or publication.

Learning requires Omi-v2 256-dimensional evidence of at least 30 seconds, at
least two voices, an owner print, owner distance greater than .50, and no manual
owner reservation. Matching uses .50 distance and .10 margin jointly against
every person print and profile. Two distinct conversations promote a candidate;
refresh must stay within .35 of every contribution. At most five contributions,
three new candidates per conversation and 25 profiles per user are retained.
Retries do not extend contribution timestamps. Rejected profiles supply negative
evidence and never identify speech. Conflicting assignments retract source
contributions and unbind. Binding requires the current person print within .35;
a drifting or missing authoritative print withdraws future naming.
Bound profiles refresh from qualifying later clusters under the same consistency
and owner-exclusion guards. Conversation retraction preserves a rejection while
any of its retained evidence remains.

The maximum contribution age is 90 days. A candidate that never recurs expires
at 30 days. Reads enforce age regardless of TTL cleanup latency. Sealed document
TTL is the earliest contribution deadline (or the candidate deadline), so a
later contribution cannot extend old evidence's physical retention. The lead
must apply `backend/deploy/recurring-voices-retention.json` through the existing
TTL runner before release. Firestore TTL deletion is asynchronous. Deletion of
a conversation retracts its contributions, including merged donors; person
deletion clears bound profiles; privacy opt-out clears all profiles atomically
with consent and increments the existing privacy generation. Account wipe
removes the user subtree. Every recurring-profile mutation reuses the account
deletion fence within its transaction. Cleanup never depends on the feature switch.
Eviction, retraction and opt-out delete removed profile documents in the same
transaction as the authority update; they never leave unexpiring empty documents.

A transcript's `recurring_voice_id` is a revocable pointer. Conversation readers
and suggestion readers honor it only while consent holds and the authoritative
profile exists, is active and is not rejected. Expiry, TTL deletion, cap eviction,
person deletion and rejection therefore immediately stop cross-conversation
linking on reads. Expiry/eviction do not sweep historical transcripts in this PR:
the inert stored pointer lasts with its transcript but is never returned or used.
Privacy opt-out also scrubs stored pointers: the cleanup pages 100 conversation
IDs at a time and re-reads/rewrites one transcript per transaction, preserving
its protection level and concurrent edits. A failed sweep propagates for retry;
repeating the opt-out retries the idempotent sweep from the start. Readers deny
links throughout cleanup, including on a sweep failure.
Processing saves recheck consent and active profile authority in their transcript
write transaction. A save before opt-out is scrubbed; a late save after the scan
cannot restore a revoked pointer. This also applies to legacy processing upserts.

Ship on by default, nested under batch-final-pass admission, with
`SPEAKER_RECURRING_VOICES_ENABLED` as the kill switch and
`SPEAKER_RECURRING_PERCENT=100` on the existing UID hash. The rollout lead owns
cohort overrides and ramp decisions. Suggestions reuse existing identify cards
and copy. `recurring_voice_id` is additive and does not require an app release;
visible pre-confirmation grouping is a later app change.
