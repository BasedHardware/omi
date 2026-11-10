# Skip L1 memory extraction for noise rows and short owner speech

Fable LLM-efficiency #7 (2026-11-10). Memory extraction (L1) ran once per
processed, non-discarded conversation and read the full transcript again. It now
skips before the model call when the row cannot yield a durable memory:

- the row is noise on Home: a server minimum, or a `media`/`noise` content kind;
- the owner spoke fewer than `L1_MIN_OWNER_WORDS` (30) words.

Unknown owner attribution is never read as owner absence. When no owner is
positively identified, the whole-transcript word count is used as an upper
bound, because the owner cannot have spoken more than the transcript. A curated
row (user title, photos, starred, folder, user-kept) always extracts, and
imported external text is not measured by words.

Nothing is written and no L1 hash is stamped on a skip, so a later reprocess
with more speech extracts normally. The skip is counted as
`omi_memory_l1_skipped_total{reason}`. Kill switch:
`EPISODE_COMPOSER_THRIFT` (default on; an explicit false word restores one
call per processed conversation).

The same PR replaces the notes/L1 reuse key's 35-file source digest with an
explicit prompt version (`config/llm_input_versions.py`), guarded by a pinned
prompt-source digest in `tests/unit/test_llm_input_prompt_version.py`. A deploy
that touches unrelated code no longer voids every stored hash.

Contract: [conversation lifecycle](../../listen_pusher_pipeline.mdx#2-conversation-lifecycle-silence-timeout-path).
Regression coverage: `tests/unit/test_l1_admission.py` and
`tests/unit/test_llm_input_prompt_version.py`. Audio custody, transcription,
wire payloads and deployment bindings are unchanged.
