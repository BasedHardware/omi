# Settle discarded register-first restore obligations

Explicit restore registers with the current durable row and `restoring=True`,
refusing deleted, tombstoned or merged-away rows before visibility metadata can
commit. Registration refusal leaves discard and user-kept metadata unchanged;
the retryable lifecycle error lets a later attempt register exactly one job.

New restore registrations carry `registration_origin=restore`. If the metadata
write fails and the conversation remains discarded, the repair and no-job seal
apply paths can settle that obligation after a `privacy_refused` seal refusal.
One transaction re-reads both documents and updates only a restore-origin
`record_pending` job to terminal queue state `privacy_blocked`, with disposition
`discarded`. A repeat is a no-op. Audio and job documents remain; no transcription,
projection, conversation metadata or other user-visible write occurs.

Planning remains read-only. Other registrations and refusal paths keep their
behavior. The helper refuses a now-visible conversation, a non-restore job, or
a job that has already advanced. No rollout flag or deployed runtime changes.

Local coverage: `test_restore_recording_obligation.py`,
`test_record_finalizer_discard_registration.py`, and
`test_restore_orphan_terminal.py`, plus the seal-caller regression suites. These
are hermetic transaction and lifecycle checks, not deployment evidence. See the
[recording pipeline contract](../../listen_pusher_pipeline.mdx).
