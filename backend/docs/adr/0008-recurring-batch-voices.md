# ADR-0008: Private recurring voices from batch finalization

Status: accepted. Decider: David, 2026-11-03 (implementation request).

Identity is automatic and inferred, with precision first and no enrollment opt-in.
Confident whole-conversation clusters may teach private, per-user profiles. An
unconfirmed profile never receives a name or creates a person. Only a manual
assignment may bind it to an existing person. The learning lane is batch
finalization; live and sync print loading never reads this roster, and there is
no streaming GPU work or retroactive refresh of past conversations.

Existing retention consent (`private_cloud_sync_enabled` and
`save_other_voice_profiles`) gates reads and writes. Profiles are AES-GCM sealed
using a per-user key and AAD binding user and voice IDs. The user document holds
ciphertext hashes as authority. Authentication, malformed data, unavailable
consent and concurrent deletion all deny publication. Transactions revalidate
the source, consent generation, account fence and person roster generation.

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

The maximum contribution age is 90 days. A candidate that never recurs expires
at 30 days. Reads enforce age regardless of TTL cleanup latency. Sealed document
TTL is the earliest contribution deadline (or the candidate deadline), so a
later contribution cannot extend old evidence's physical retention. The lead
must apply `backend/deploy/recurring-voices-retention.json` through the existing
TTL runner before release. Firestore TTL deletion is asynchronous. Deletion of
a conversation retracts its contributions, including merged donors; person
deletion clears bound profiles; privacy opt-out clears all profiles atomically
with consent and increments the existing privacy generation. Account wipe
removes the user subtree. Cleanup never depends on the feature switch.

Ship on by default, nested under batch-final-pass admission, with
`SPEAKER_RECURRING_VOICES_ENABLED` as the kill switch and
`SPEAKER_RECURRING_PERCENT=100` on the existing UID hash. The rollout lead owns
cohort overrides and ramp decisions. Suggestions reuse existing identify cards
and copy. `recurring_voice_id` is additive and does not require an app release;
visible pre-confirmation grouping is a later app change.
