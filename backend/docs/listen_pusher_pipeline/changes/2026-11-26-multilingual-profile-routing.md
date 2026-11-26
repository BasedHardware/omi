# Multilingual-profile routing (SCA-4810)

Contract: [batch admission language](../../listen_pusher_pipeline.mdx), the `multilingual_profile` paragraph.

**Problem.** Migration 006 made multi-language the default for English users, and the app stamps the app
language (`en`) on every conversation. `batch_admission_language` treated that pin as proof Parakeet could
serve the audio, so a Mandarin/English speaker's uploads went straight to batch Parakeet (25 European
languages, no `zh`) with no LID. On one owner's evening of Mandarin/English conversation, every upload
admitted to Parakeet came back with no Chinese text. Only the overflow sent to legacy Velma carried any.
Failure class: FC-unknown-language-treated-as-model-capability.

**Change.** A multi-language user whose own rolling live-STT language profile shows unsupported speech
(at least 2 sessions with 10 or more segments in batch-unsupported codes, making up 20% or more of the session's classified segments; `und` counts in neither; the projection counts segments, not words) no longer gets
the pin trusted. Admission returns `multilingual_profile`.
- With legacy ON, sync intake samples it on audio like `unknown_multilingual_conversation`: vendor LID on
  the first speech window, then the self gate on every later window. Only an all-supported upload is
  admitted, otherwise it stays on legacy multilingual STT.
- In the record lane, a new owner goes to legacy, which runs per-file LID.
- With legacy draining or dark, the upload enters batch as `multi`. Batch inheritance never takes such a
  user's pin, so an existing record-lane `batch_sync_v1` owner (which skips admission) is classified per unit too.

The profile is read from the user document intake already loads, so there is no new I/O.

**Lab evidence.** Pipeline lab `stt_routing`, on a private copy of the owner's real audio (72 recordings,
about 10,400 s; never committed), replaying recorded LID answers. Arms are current vs. this change. The
speech reference comes from Velma's CJK-script words. Unsupported speech sent to Parakeet fell from about
2,300 s (100%) to about 200 s (8.5%), and recordings on Parakeet fell from 72 to 24. That took 232 vendor
probes and 50 self-gate windows.

**Rollout.** Ship on behind the kill switch `BATCH_MULTILINGUAL_PROFILE_ROUTING_ENABLED=false`, which trusts
the pin again (`BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED=false` restores it too). The signal depends on
`STT_LEARNED_LANGUAGE_PROFILE` staying on: the live session projection is written only while it is, and a
lapsed profile silently returns flagged users to the pinned route. Readback: `outcome=reclassified` log count, and the multilingual intake route share for
profiled users, after backend-sync serves it.

**Not changed.** The multilingual engine choice (Soniox did best on code-switching in the lab), word
joining in Velma output, and live STT language labelling (Mandarin labelled `ja`) are follow-ups.
