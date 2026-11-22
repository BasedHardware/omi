# Bound Home Processing presentation (UO-1107-01)

The [Home age contract](../../listen_pusher_pipeline.mdx#home-processing-presentation-age)
limits the list's processing classification for stranded `processing` or `merging`
conversations. At six hours the list projects `home_step=failed`; storage, status writers,
lifecycle, finalization, search and direct links remain unchanged.

S5 ports the unpublished `lane/lchomeage` implementation and its curation-test
correction onto current main. Source records: bus rows `6b0721` and `c36cb8` in
`omi-workspace/data/run-2026-10-13-two-lane-nemotron/swarm/bus.jsonl`.

## Clock and bound

`processing_admitted_at` looks like an entry time but is a renewable lease:
`processing_admission_guard` renews it while an inline processor runs. There is
no stored `processing_started`. Use the first usable datetime in `finished_at`,
then `created_at`. Capture end is a stable proxy, not an exact processing-entry
time. For delayed imports or a merge of old captures it can predate the current
attempt; an active attempt may therefore present as Failed. `created_at` can
also be recorded time on imports. No immutable entry stamp can be introduced
within this presentation-only PR. `started_at` measures recording start;
`updated_at` tracks unrelated progress. Neither is a processing-age authority.
Without either fallback datetime, preserve today's step and count the gap.

Normal finalization is expected to take minutes; batch STT has a two-hour SLA.
`HOME_PROCESSING_MAX_AGE_SECONDS=21600` gives six hours of headroom and is
adjustable by lead2. Invalid, blank, zero and negative settings use six hours
and are counted; they never silently disable the bound.

Curation (user title, star, folder, photos) still protects **completed** rows.
Processing already precedes curation in `classify`; preserving that ordering
avoids claiming unfinished curated content is Ready or keeping it Processing
forever. Old curated processing rows also project Failed. This changes no
content or access policy.

## Readers and client

- `home_step.project` has one serving caller: main `GET /v1/conversations`, before
  `transcribing_hold.project`. Both full and indexed list copies include
  `finished_at` and `created_at` through the existing Conversation model fields.
- Shared database hydration remains authoritative; it does not classify or
  persist Home steps. No new field selection or query is necessary.
- Conversation detail, shared detail, folder, developer/integration/MCP lists,
  browse/search and task reads use only the existing transcription presentation,
  not `home_step.project`; they do not inherit this bound.
- `app/lib/pages/conversations/home_rows.dart` honors server `failed` before
  status inference and hides failed standalone rows. However, the tracked-row
  reconciliation can replace list rows with detail results and reinsert their
  stored `processing`/`merging` status through `_withProcessingRows`.
  `ProcessingConversationRow` does not consume `homeStep`; episode pending-member
  handling also maps a failed member to Writing notes. This backend change alone
  does not guarantee a visible fix in Flutter. Client work is outside S5.
- macOS and web do not consume `home_step` for Processing. No cross-client UI
  outcome is claimed by this server contract change.
- Writer-version conditional GETs are disabled while Home projection is on,
  including when the separate transcription gate is off. Time alone can now
  change the projected step.

## Rollback and evidence limits

On by default under the existing `HOME_STEP_PROJECTION` kill switch. Set it off
to omit the field and restore client inference; increase the positive age setting
to extend the wait. There is no data migration or lifecycle rollback.
`omi_home_processing_age_total` counts classification calls, not unique rows or
per-request totals. Reasons use a closed enum; no IDs, titles or content are labels.

Hermetic classifier tests freeze time immediately before, at, and after six hours
for both statuses, both fallback clocks, and titled/untitled rows. Indexed-reader
and API serialization tests cover the bound,
fallback clocks, invalid config, curation, kill switch and unchanged stored state.
No GCP/prod reads were performed. The number of affected production rows was
**not measured**; that needs a separately authorized read-only aggregate.
No deployed or rendered-app acceptance is claimed.
