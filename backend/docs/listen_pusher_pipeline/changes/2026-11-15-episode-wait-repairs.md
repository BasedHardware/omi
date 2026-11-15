# Episode wait and empty-member bug repairs

The all-members-complete compose gate, episode boundaries and audio lifecycle are unchanged.

`EPISODE_COMPOSE_SETTLED_TERMINAL_ENABLED` defaults on. A completed row with an exhausted-output or settled below-floor decision, no rendered summary/receipt and no renewed summary debt is settled; it never starts or extends the transcript wait. Empty text without that affirmative terminal decision retains the existing wait. This reuses the Home noise classification's inputs independently of presentation switches. Late speech still changes the fingerprint/evidence and triggers the normal receipt wake. Off restores the empty-transcript wait. No terminal state or recording status is written. Old images may still wait during mixed rollout; new images ignore that false blocker on reevaluation. No model-version bump or fleet regeneration.

Every composer host must receive these repairs: backend, backend-integration, backend-sync, backend-sync-backfill and listen/any process starting `main.py`'s local retry task. No GPU image or provider backlog change. All validation is local; integration/rollout/physical Home acceptance belongs to the lead.
