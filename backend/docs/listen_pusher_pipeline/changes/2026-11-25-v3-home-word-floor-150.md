# V3 Home word floor lowered from 300 to 150 words

`MIN_HOME_WORDS` in `utils/conversations/v3/word_floor.py` is now 150 (product owner decision,
2026-11-25). A finished, non-manually-ended v3 conversation with fewer than 150 words (script-aware
count) is still hidden from Home with `home_hidden_reason='below_word_minimum'`; conversations of
150–299 words are now shown.

Why: in dogfooding, a 269-word conversation the wearer wanted on Home was hidden.

The same constant also sets, unchanged in shape:

- the notes tier: windows at or above the floor get full notes instead of short tasks
  (`process_conversation._get_structured`), and on-open summary eligibility (`summary.summary_eligible`);
- planner topic folding and sit-down joining (short topics fold into the next topic that meets the floor);
- the backfill and live re-derive estimates.

`MIN_TASK_WORDS` (20) is a separate floor and does not change. The notes agent's 300-word evidence
threshold (`CONVERSATION_NOTES_AGENT_ENABLED`) is a separate rule and does not change.

There is no flag. Rollback is a revert of the constant. Existing rows keep their stored visibility
until a rebuild re-projects them; new and rebuilt windows use the new floor.

Readback after serving: the share of newly committed, finished, non-manual v3 windows with
`home_hidden_reason='below_word_minimum'` should fall compared with the same window before the change.
No Prometheus series counts Home visibility by reason; read it as an aggregate count over derived
conversations.

See the [v3 pipeline contract](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3).
