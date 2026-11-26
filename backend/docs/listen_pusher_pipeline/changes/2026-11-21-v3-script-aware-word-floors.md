# Script-aware v3 transcript minimums

[Recording-derived conversations v3](../../listen_pusher_pipeline.mdx#recording-derived-conversations-v3)
counts Han, kana, Hangul and Thai letters as individual units and keeps the
whitespace count for other text. Home projection, automatic processing, opening
notes and backfill estimates use that count for the 20- and 300-word minimums.

The backend applies this by default. Revert the change to roll it back. Newly
eligible conversations use the existing tasks or notes path. The count uses
already-loaded text and adds no datastore or vendor calls per evaluation.

For the first full post-train measurement window, sum the increase in
`omi_conversations_v3_word_floor_completions_total` by `method` and `floor`
over v3 processing replicas. For each method (`legacy` and `script_aware`),
report the total and the fraction labeled `below`. Both methods measure the
same settled cohort of first-pass automatic conversations containing the
target scripts. Record the window and both shares, and use the script-aware
share as the prospective baseline. The metric contains no transcript or
conversation identifiers and adds four counter series per replica to the
backend-sync scrape profile.
