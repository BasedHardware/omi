# Soniox first for languages Parakeet cannot serve (batch route table)

**What changed.** The prod batch vendor route table moves from `en-overflow-1116` to `soniox-unsupported-1127`
(`backend/deploy/batch-pipeline/vendor_route_table.prod.json`, served as `BATCH_VENDOR_ROUTE_TABLE` on the sync
services):

- `gpu_unsupported` units (languages Parakeet cannot serve: Mandarin, Japanese, Korean, Hindi, Arabic, Hebrew and
  others) start on Soniox, with Modulate Velma as failover. They used to start on Velma.
- Soniox is no longer failover-only, and has no daily audio-hours cap or monthly budget. The code lock that made
  every table keep Soniox failover-only (`FAILOVER_ONLY_SERVICES`, a lead rule from 2026-11-01) is removed;
  `failover_only` stays a per-table choice.
- A new paging alert, `omi-batch-soniox-daily-hours`, fires when batch Soniox audio passes 1,500 audio-h in 24 h
  (about $180 at the $0.12/h list price). It replaces the cap, so user growth never holds units on a cap.
- English and the other Parakeet languages stay on the GPU. Fresh English still overflows to Modulate past the
  GPU SLO. With Modulate down too, it now overflows to Soniox instead of waiting.

**Why.** David, 2026-11-27: Soniox for the speech that needs it, per unit. A public eval through the production
clients (FLEURS dev, 12 languages, plus ASCEND code-switched Mandarin/English, in 60 s blocks) had Soniox ahead of
Velma on every language except English, where they tie. For example, Mandarin CER was 8.4% vs 21.8%, Hindi WER 8.3%
vs 33.6% and Japanese CER 4.1% vs 12.8%; p95 latency per 60 s file was 5.3 s vs 23.7 s. The harness and results are
in omi-workspace `data/run-2026-11-26-multilang-stt-lab/eval/`.

**Reach.** The table serves owners in the `batch-vendor-routing` ramp (25% on 2026-11-27; David asked for 100% the
same day). Owners outside it keep the built-in route (Modulate for these languages).

**Cost.** Before the change, about 528 audio-h/day of batch Modulate and 132 of Soniox (24 h to 2026-11-27T05:5xZ).
At 100% vendor routing, moving unsupported-language units from Velma ($0.06/h) to Soniox ($0.12/h) adds roughly
$30–75/day: today's units, plus the multilingual-profile units that #26431 classifies per unit. The page bounds it.

**Rollback.** Put `en-overflow-1116` back into `BATCH_VENDOR_ROUTE_TABLE` on the sync services. Units already
admitted keep their route.
