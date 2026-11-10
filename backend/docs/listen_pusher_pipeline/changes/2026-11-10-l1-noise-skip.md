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
`EPISODE_COMPOSER_REUSE` (default on; an explicit false word restores one
call per processed conversation).

The same PR replaces the notes/L1 reuse key's 35-file source digest with an
explicit prompt version (`config/llm_input_versions.py`), guarded by a pinned
prompt-source digest in `tests/unit/test_llm_input_prompt_version.py`. A deploy
that touches unrelated code no longer voids every stored hash.

Contract: [conversation lifecycle](../../listen_pusher_pipeline.mdx#2-conversation-lifecycle-silence-timeout-path).
Regression coverage: `tests/unit/test_l1_admission.py` and
`tests/unit/test_llm_input_prompt_version.py`. Audio custody, transcription,
wire payloads and deployment bindings are unchanged.

## Review dispositions (L8a)

The independent EPISODE_COMPOSER_REUSE kill switch restores source-derived key writes and L1 admission. Both modes accept current stable keys and compatible pre-deploy source keys, so toggles do not buy unchanged eligible work. Historical aliases are pinned from main source history with identical prompt and routing sources and locked dependencies; changed inputs and unusable outputs still miss. Routing bytes independently invalidate stable keys. No backfill or forced gist regeneration. Normal gates, then watch exact-input misses/skips and memory yield; refactor-lead owns rollback.

Installed `pydantic` and `langchain-core` versions are read once at import and
included in both key modes. Historical aliases additionally require the exact
recorded versions (`2.11.10` and `1.3.3`), preserving deploy reuse at today's
locks. A future dependency bump deliberately invalidates prior checkpoints:
on next processing, unchanged input needs one successful notes recomputation
and one successful L1 recomputation if admitted, then reuses again. This is
bounded to work actually reprocessed, with no proactive backfill; existing
provider retries and concurrent processing can add calls before success is
persisted. Regression tests cover both dependency upgrades, locked-version
aliases, kill-switch flips and repeated processing after recomputation.
