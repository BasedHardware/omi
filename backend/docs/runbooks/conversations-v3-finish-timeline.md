# v3 manual Finish timeline (Prometheus)

Objective (2026-11-27): after a manual Finish on a v3 recording, the summarized card shows on Home within
p90 < 60 s, and ideally p50 <= 20 s. This page gives the server-side Prometheus readout of that number and how
it splits across stages. The client-measured, log-based SLI (Finish cut to first Home summary, SCA-4489) is
in `v3-finish-home-sli.md` once it lands. That readout scores the cohort. This one shows
where the time goes.

Every observer reads a row its caller already holds and records after its own commit. No Firestore reads or
writes are added. Labels are static: `stage`, and `path` (the Finish stamp's `tail`, `newer` or
`newer_dual`). There is never a uid or conversation label. Code:
`utils/conversations/v3/finish_timeline.py`.

## Families

| Family | Anchor | Who is measured |
| --- | --- | --- |
| `omi_conversations_v3_finish_to_visible_seconds{path}` | Finish request (`v3_finish_requested` stamp) | Stamped Finishes, at the first visible manual-end settlement |
| `omi_conversations_v3_finish_stage_seconds{stage,path}` | Finish request (stamp) | Stamped Finishes, at every stage |
| `omi_conversations_v3_manual_end_stage_seconds{stage}` | The row's `finished_at` | Every manual-end card, stamped or not |

Only the live-window Finish writes the stamp: `request_finish` (no legacy row in progress). It is the only
anchor at the Finish request itself. A Finish that runs through the in-progress conversation's finalization
job stores no stamp, and that is most v3 Finishes today. Those Finishes appear only in
`manual_end_stage_seconds`. That family's anchor is the recording's end at `admitted` and `transcript_fast`,
and the card's last speech from `builder_started` on. It is the "cut" that Firestore cut-to-summary samples
use. A Finish tapped after trailing silence therefore reads longer there than from the tap.

Stages, in order (`metrics.FINISH_TIMELINE_STAGES`):

| Stage | Where | Moment |
| --- | --- | --- |
| `admitted` | backend-integration, record admission | The manually finished recording's audio was admitted (first admission before its cut is stored) |
| `transcript_fast` | backend-integration, fast finish | The fast first transcript was written. Batch-only Finishes have no sample here |
| `builder_started` | backend-sync, builder | Start of the pass that first committed the card as manually ended |
| `card_finished` | backend-sync, builder | That pass's commit: Home shows the ended card, writing its summary |
| `notes_started` | backend-sync, notes | First notes attempt began. Cards that settle without notes (media, background) have no sample here |
| `summary_visible` | backend-sync, settle | First visible manual-end settlement, with the summary. For stamped Finishes it equals `finish_to_visible` |

Both services deploy with `deploy/cloud_run_gmp_sync.yaml`, whose keep-list names these families. A family
missing from that list has no series at all.

## PromQL

Read through the GMP query API with the `ro-prod` identity. Use a `[1d]` window, or `[6h]` for a quick check.
Do not filter stage queries by `service_name`: the stages are observed on two services.

Headline, for stamped Finishes:

```promql
histogram_quantile(0.5, sum by (le) (rate(omi_conversations_v3_finish_to_visible_seconds_bucket[1d])))
histogram_quantile(0.9, sum by (le) (rate(omi_conversations_v3_finish_to_visible_seconds_bucket[1d])))
sum(increase(omi_conversations_v3_finish_to_visible_seconds_count[1d]))
```

Per stage, from the Finish request:

```promql
histogram_quantile(0.5, sum by (le, stage) (rate(omi_conversations_v3_finish_stage_seconds_bucket[1d])))
histogram_quantile(0.9, sum by (le, stage) (rate(omi_conversations_v3_finish_stage_seconds_bucket[1d])))
sum by (stage) (increase(omi_conversations_v3_finish_stage_seconds_count[1d]))
```

Per stage, from the cut, for every manual-end card (the readout available for job-path Finishes):

```promql
histogram_quantile(0.5, sum by (le, stage) (rate(omi_conversations_v3_manual_end_stage_seconds_bucket[1d])))
histogram_quantile(0.9, sum by (le, stage) (rate(omi_conversations_v3_manual_end_stage_seconds_bucket[1d])))
sum by (stage) (rate(omi_conversations_v3_manual_end_stage_seconds_sum[1d]))
  / sum by (stage) (rate(omi_conversations_v3_manual_end_stage_seconds_count[1d]))
```

To find the untracked waiting, take the difference of mean stage times. The two `stage` values come from the
same family and window:

| Gap | What it holds |
| --- | --- |
| `transcript_fast` (or `admitted`, batch-only) to `builder_started` | The wake or queue wait before the pass that applies the cut, including held passes (`omi_conversations_v3_finish_held_total`) |
| `builder_started` to `card_finished` | The pass itself (outline model, commit: `omi_conversations_v3_builder_commit_seconds`) |
| `card_finished` to `notes_started` | Wait for the processing drain |
| `notes_started` to `summary_visible` | The notes model (`omi_notes_agent_latency_seconds`) and the settle |

The differences are exact only between means over the same Finishes. A quantile of one stage minus a quantile
of another is a guide, not an exact split, and batch-only Finishes have no `transcript_fast`.

Supporting families on the sync profile: `omi_conversations_v3_end_to_summary_seconds` and
`omi_conversations_v3_first_speech_to_visible_seconds` use the default buckets, which top out at 10 s, and
they cover every summary, not only manual ends. Use only their mean (`_sum / _count`). The others are
`omi_closed_to_summary_seconds{lane}`, `omi_conversation_processed_seconds{lane,basis}` and
`omi_conversation_settled_unsummarized_total`.

## Limits

- Only the live-window Finish is anchored at its request. To anchor finalization-job Finishes, the capture
  close would also have to stamp the recording row from the job's `created_at`. That is a new field on an
  existing write, so it needs a `DESIGN:` review before it is built.
- `admitted` counts the first admission before the cut is stored. `card_finished` counts the first commit
  that ends the card. `notes_started` counts the first notes attempt. `summary_visible` counts the first
  visible settlement. A retry of the same stage on another instance can add a later sample.
- Stamps and cuts older than two hours (`FINISH_STAMP_MAX_AGE`) are dropped, not observed.
