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

## The rephraser (`utils/llm/user_voice_rephrase.py`)

The polish fixes marks; the rephraser changes the words. It was measured on one real
user's own sent texts (the user ran it on their own messages, locally; none of the text
is in this repo). 285 held-out replies to 9 people, each paired with a plain draft of the
same meaning written by a model from the real reply. Each system rewrote the plain draft
from the user's past texts to that person; every rewrite went through the same `guard`.
A blind Opus judge, one reply per call with no tools, saw the user's past texts, the
draft, the real reply and every system's text shuffled, and scored each 0-100 for "this
person typed it", plus whether it keeps the draft's meaning.

| system | "they typed it" (0-100) | scored at least as high as the real reply | keeps meaning | p50 latency |
|---|---|---|---|---|
| the user's real reply | 38.1 | -- | 81% | -- |
| plain draft, polished only | 26.0 | 32% | 100% | 0 |
| Qwen3-0.6B, no adapter | 24.9 | 31% | 98% | 0.15 s |
| Qwen3-0.6B + LoRA (700 steps) | 38.4 | 55% | 88% | 0.14 s |
| Qwen3-0.6B + LoRA (1400 steps) | 35.5 | 50% | 82% | 0.16 s |
| Opus, same prompt | 42.4 | 64% | 98% | 6-8 s |

The adapter (rank-8 LoRA on 16 layers, 11 MB) was trained with `mlx_lm lora --mask-prompt`
on rows whose prompt is exactly `rephrase_messages(...)`, from the user's other replies;
validation loss was lowest at 700 steps and rose after, which the judge confirms. The
judge's "keeps meaning" counts shortening as a change: it says 19% of the user's own real
replies do not keep the plain draft's meaning. Of the adapter's misses, most are shorter
replies ("Thank you so much" for "Thank you so much. This is really helpful."); the
loops a 0.6B model makes at temperature 0 ("Omggg..." x60, "the journal of the journal")
are refused by `guard` ("repeats itself") and the draft goes out instead.

Serving: `mlx_lm.server --model mlx-community/Qwen3-0.6B-bf16 --adapter-path <dir>` with
`USER_VOICE_REPHRASER_URL=http://127.0.0.1:8080/v1` and the model left at its default,
`default_model` (mlx_lm applies `--adapter-path` only to that name).
