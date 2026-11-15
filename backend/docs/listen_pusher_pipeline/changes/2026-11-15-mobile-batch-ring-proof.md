# Mobile Standard batch publishes durable pendant custody

The app's exclusive Standard batch route now retains exact device/ring/live
session coordinates and publishes phone custody through the ordinary mark-pair
and contiguous-frontier validator after audio fsync and WAL index persistence.
The app-only journal survives process death without interpreting old ordinals
in a new connection. An unindexed journal, partial mapping or missing oldest
prefix still retains pendant audio. There is no backend, pusher, wire-protocol
or firmware change.

Contract: `app/lib/services/wals/CUSTODY.md` and
`app/lib/services/wals/PENDANT_RING_CUSTODY.md`. Default on; rollback is the
compile-time `OMI_BATCH_RING_PROOF_OFF=true` switch. The real-file/fake-pendant
state-space guard is `app/test/services/wals/batch_ring_proof_test.dart`, including
a separate compile-time OFF run. Physical firmware 3.0.24 acceptance still
requires Device Storage used to fall while connected, with fresh paired unread
bytes and ring read/write/drop counters; local tests do not establish that gate.
