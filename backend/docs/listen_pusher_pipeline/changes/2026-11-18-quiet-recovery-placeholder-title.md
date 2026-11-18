# Quiet recovery of a capture with a placeholder title

An already admitted server-recovery job can use the existing short-clip
minimum when its stored title is the deterministic fallback and the row holds
no rich content, Home gist or previously generated metadata. Previously the fallback title sent the job to
paid notes, where empty output could dead-letter a capture that could have
settled on the minimum. The user title, relevance, transcript and custody
checks still apply. Admission, discard eligibility and final-attempt processing
are outside this change.

Deploy to the backend finalization worker with the existing
`LISTEN_FINALIZATION_RECOVERY_MINIMUM_TERMINAL_ENABLED` setting. Check the
`selfheal_guard` events for `kept_minimum/content_below_floor` and finalization
dead letters after the rollout. Revert the commit if the change regresses
quiet recovery.
