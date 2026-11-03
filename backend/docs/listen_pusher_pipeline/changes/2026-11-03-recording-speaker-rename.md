# Name a voice across its recording

Recording-wide edits apply the existing same-scope carry rule to every episode
member, including earlier members. The all-user conversation entry point also
covers same-scope conversations without episode membership. Each member retains
its own replayable receipt. An encrypted latest-decision map lets later rollovers
inherit a late correction even when the preceding member has no such voice.
Legacy rows use the existing deterministic segment IDs and conversation-local
speaker matching. Diarization, embeddings and cross-scope voice linking are unchanged.

Mobile naming defaults to the recording and reports the applied line count.
Selection spans member transcripts and sends one grouped assignment request.
Naming remains available while notes regenerate; live edits queue. A stale-speaker
409 restores optimistic labels and asks the user to select the lines again.

Deploy API and live receipt/carry consumers before shipping the mobile build.
There is no new feature flag or kill switch. Existing episode admission remains;
the conversation entry point provides recording correction outside that cohort.
Only the rollout lead deploys.

The [receipt and ordering contract](../../listen_pusher_pipeline.mdx#transactional-manual-speaker-boundaries)
defines fan-out, scope fencing, legacy behavior and trailing regeneration.
Fixture evidence lives in
[backend regressions](../../../tests/unit/test_recording_speakers.py),
[mobile selection tests](../../../../app/test/widgets/recording_speaker_selection_test.dart)
and the [before/after render manifest](../../../../.agent-artifacts/ui-evidence/lane-speakerrename/evidence.json).
