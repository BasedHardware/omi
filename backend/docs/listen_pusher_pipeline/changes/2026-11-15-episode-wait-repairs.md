# Episode wait and empty-member bug repairs

The all-members-complete compose gate, episode boundaries and audio lifecycle are unchanged.

`EPISODE_COMPOSE_SETTLED_TERMINAL_ENABLED` defaults on. A completed row with an exhausted-output or settled below-floor decision, no rendered summary/receipt and no renewed summary debt is settled; it never starts or extends the transcript wait. Empty text without that affirmative terminal decision retains the existing wait. This reuses the Home noise classification's inputs independently of presentation switches. Late speech still changes the fingerprint/evidence and triggers the normal receipt wake. Off restores the empty-transcript wait. No terminal state or recording status is written. Old images may still wait during mixed rollout; new images ignore that false blocker on reevaluation. No model-version bump or fleet regeneration.

Every composer host must receive these repairs: backend, backend-integration, backend-sync, backend-sync-backfill and listen/any process starting `main.py`'s local retry task. No GPU image or provider backlog change. All validation is local; integration/rollout/physical Home acceptance belongs to the lead.

## Per-blocker wait cap

`EPISODE_COMPOSE_ANCHORED_WAIT_ENABLED` defaults on. The additive `compose_transcript_wait_observations` map stores `pending_at` and `observed_at` per member. A continuing blocker generation keeps its observation across membership/blocker changes; a new pending stamp receives its own limit. Legacy blockers seed from the existing aggregate wait start. Each member deadline is the earlier of pending+limit and first-observed+limit; the effective wait is the earliest deadline of the currently blocking set. Expired observations survive unrelated receipt clearing so another blocker cannot renew them. Late transcripts and new pending generations are reevaluated normally.

Old images ignore the map and may rewrite/clear legacy aggregate wait fields. New readers cap those fields using the per-member observations, so old membership resets cannot extend an already-observed blocker. Off ignores the map and restores aggregate-start reset behavior. The existing transcript-wait enable switch and 1,200-second limit remain authoritative. No new index or production migration.
