# Daily recap depth

Daily recap depth is an account preference stored as `users/{uid}.daily_summary_depth`.
The allowed values are `brief`, `normal`, and `deep`. A missing or malformed value
reads as `brief`, preserving the existing recap prompt for older accounts.

`GET /v1/users/daily-summary-settings` returns `depth` alongside the existing
notification `enabled` and `hour` fields. `PATCH` accepts an optional `depth`;
unsupported values return 422. When a depth is patched, the response echoes it
so a new client can detect an older backend that ignored the field. Existing
enabled/hour-only PATCH calls keep their `status: ok` contract.

Generation reads the stored preference at the start of each new summary. Brief
keeps the current short guidance; Normal asks for more context and up to eight
useful items per section; Deep Reflection removes fixed item counts and asks
for grounded connections and patterns. Deep alone reads at most three older
recaps (before the target date) and three active goals, with bounded text, so
it can connect actual prior context rather than inventing it. Those optional
reads fail soft with fallback telemetry; Brief and Normal make no extra reads.
All three use the same JSON payload shape. No old recap is regenerated or
silently rewritten when the preference changes.

Deploy the backend before shipping the desktop picker. A desktop build against
an older backend treats a depth PATCH without an echo as unsaved and restores
the previous picker value; it never shows a false saved state.
