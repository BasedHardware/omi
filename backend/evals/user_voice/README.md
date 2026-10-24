# User voice eval (propose_message drafts, #23541)

`fixtures.json` holds three invented people the same user writes to differently
(a sister in mixed English and Chinese, a manager in formal English, a friend in
Chinese). For each: the user's own lines (the profile source), held-out real lines,
and drafts a generic chat model wrote for the same intents. No customer records,
database reads or model calls.

`backend/scripts/user_voice_eval.py` builds each profile with
`utils.llm.user_voice.build_profile`, polishes every draft with `polish_draft`, and
runs a blind code judge: shown a held-out real line and a draft in random order, it
picks the one closer to the profile's marks (ending, "!" count, emoji, script). A
draft the judge cannot tell apart from the real line scores as a tie. It reports how
often the judge spots the draft before and after polish; lower is better.

```sh
backend/.venv/bin/python backend/scripts/user_voice_eval.py
```

Success: after polish the judge spots the draft in at most half the pairs, and in
fewer pairs than before polish. The polish never changes words, so this measures
marks only; the prompt block's effect on wording needs a live model run against
the dev gateway (same procedure as `evals/dream_triage`), which this eval does not
claim.

`results.json` is the last recorded run.
