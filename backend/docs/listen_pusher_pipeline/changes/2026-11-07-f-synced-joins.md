# Variant F for synced and late joins

Sync (offline WAL) and late live conversations used to join their recorded-time owner without the
F boundary, so an ambiguous join (2 to 30 minutes after the owner's last speech) was never asked about.
Now such a join asks F with the conversation's full transcript before it is placed. A moved-on answer
splits it into its own occasion under the same member guard as the live path.

Authority and scope:

- The candidate's privacy is checked against the stored document right before the model call, not
  against the intake snapshot, and fails closed when the document is missing.
- The owner is the episode attachment would choose: the candidate's start point, over the same window.
- Every other outcome keeps today's join: outside the cohort, killed, too little speech, a short gap,
  already placed, an error at any step, or a failed close of the owner.
- A sync attach asks Jev at most once. Lost-CAS retries reuse the first answer and close the owner at most once.

Rollout and flags: the flag-store rule `episode_f_join`, with the environment fallback
`EPISODE_F_JOIN_PERCENT` (default 0) and the kill switch `EPISODE_F_JOIN_ENABLED`. Both must be set
for the cohort; the default keeps every join as today's.

Verification: `backend/tests/unit/test_episode_f_join.py` (candidate exclusions, lost-CAS retries,
stale-snapshot privacy, close failures, split and keep outcomes), `test_episode_f_join_guards.py`, and the
sibling episode attach suites. The People-generation inventory pin is unchanged.

Related contract: the synced intake path in `backend/utils/episodes/service.py` (`_attach_recorded_synced`).
