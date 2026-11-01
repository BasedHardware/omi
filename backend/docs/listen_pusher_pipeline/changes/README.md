# Listen + Pusher pipeline change notes

One file per change, named `YYYY-MM-DD-<short-slug>.md`. Two PRs never edit the same note, so pipeline
documentation no longer forces a merge of `main` into every audio, transcription or lifecycle branch.

Between 2026-10-18 and 2026-11-01, 165 fleet PRs edited `backend/docs/listen_pusher_pipeline.mdx` and 77 of them
had to merge `main` back in. Each catch-up re-ran the pre-push gate and a full CI cycle.

## What goes where

- **Change notes go here.** This covers what changed, why, the rollout and flag state, and the evidence links:
  the narrative sections that used to be appended to the pipeline doc.
- **Contracts stay in `../../listen_pusher_pipeline.mdx`.** That means env vars and their defaults, wire and
  payload fields, ordering and idempotency guarantees, and the sequence diagrams. Tests and the flag registry cite
  that file directly (for example `tests/unit/test_vad_cache_ttl_config.py`), so edit the contract section there
  when a contract changes.

A note links to the contract section it changes. Notes are folded into the pipeline doc periodically, in one
docs-only PR that deletes the folded notes.
