# User Voice Blind Eval (`propose_message`)

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
whether the blind style judge can distinguish the polished draft from a held-out
real line written by the user to that same person.
