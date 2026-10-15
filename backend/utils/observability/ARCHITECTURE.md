# Backend observability

This package records bounded operational signals and owns their presentation/export. Callers provide outcomes and scalar timings; metrics must not contain user, recording, job or conversation identifiers. It does not own pipeline decisions or persistence.

| Module | Responsibility |
| --- | --- |
| `journeys.py` | Product journey outcomes and elapsed time |
| `transcription.py` | Live/batch transcription attempt outcomes and bounded counters |
| `sync_phases.py` | Context-scoped sync phase latency/calls and request-bound aggregate export |
| `finalization.py` | Finalization outcomes |
| `fallback.py` | Shared fallback telemetry |
| `speaker_identification.py` | Speaker decision/review metrics |
| `speaker_learning_jobs.py` | Voice-learning job event metrics |
| `speaker_tag_prompts.py` | Speaker prompt telemetry |
| `subscription_events.py` | Bounded billing/subscription events |
| `api_keys.py` | API-key observability |
| `langsmith.py` | Trace integration |
| `langsmith_prompts.py` | Cached prompt retrieval and rendering |

Shared Prometheus definitions and HTTP exposure live in `utils/metrics.py` and `routers/metrics.py`. Runtime gates are declared in `config/feature-flags.yaml`; deploy sources live under `backend/deploy/runtime_env/`. Sync export/rollback acceptance is documented in [the runbook](../../docs/runbooks/sync-cloudrun-rightsizing.md).
