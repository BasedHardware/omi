# User Voice Feature Consistency Eval (`propose_message`)

Evaluates whether per-person user voice profiling (`backend/utils/llm/user_voice.py`)
and its deterministic polish pass produce message drafts that match the user's
real lines to that recipient (ending punctuation, `!` count, emoji rate, and
opening casing).

## Running

From the repository root:

```sh
python backend/evals/user_voice/eval_blind.py
```

The script builds each recipient's `UserVoiceProfile` from `fixtures.json`,
polishes the candidate draft with `polish_draft_in_user_voice`, and checks
whether those four style features diverge from a held-out real line written by
the user to that same person. This is a deterministic feature consistency check,
not an independent blind judge or evidence that people cannot distinguish the
draft from real messages. The polish pass optimizes these same features, so a
perfect fixture score is expected and does not measure overall voice quality.
The historical `polished_indistinguishable_from_real` output key counts only
this feature-level comparison; it makes no human indistinguishability claim.
