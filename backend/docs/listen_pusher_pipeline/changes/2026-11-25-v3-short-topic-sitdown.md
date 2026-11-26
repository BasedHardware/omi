# Keep delayed short topics in one v3 sit-down

With the default five-minute timing, speech that arrived more than five minutes
after capture could lock immediately. A subsequent batch with a short recorded
gap could outline with that speech, but the earlier committed card kept its
transcript and audio claims. Each batch could become its own hidden short card.

Live stretch cohesion now uses the later of recorded speech end and transcript
landing to decide when to settle, including at the default timing. The
five-minute boundary between recorded speech stretches still applies, as do
manual End, the duration cap, and the 150-word Home floor. Media and background
retain their independent projection. Historical derivation and previously
committed custody follow the existing rules.

Set `CONVERSATIONS_V3_SETTLE_ON_LANDING=off` to restore the recorded clock
at the default timing. Custom timing already uses the landing clock. The switch is
documented with the other v3 switches in the
[v3 model contract](../../listen_pusher_pipeline.mdx).
