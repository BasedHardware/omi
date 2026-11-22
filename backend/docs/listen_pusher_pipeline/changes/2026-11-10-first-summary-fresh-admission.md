# Reserve fresh enrichment admission for pending first summaries

New/reopened bindings, idle primary-queue promotion and unbound-row repair now
require `first_summary_pending(row)` as well as the existing conversation recency
window before selecting the fresh queue. Recent summary refreshes stay on the
primary queue. Effects and completed-summary backfill keep their existing routing.
The row already carries summary state, so this adds no Firestore read and skips
the conversation-clock lookup for refreshes.

Handler, audience and invoker checks, active-lease fences and token rotation are
unchanged. In-flight rows keep their current binding until their next re-bind.
The change takes effect with the backend release and adds no flag or queue config.
Rollback is a revert; keep existing queues running so stored bindings can drain.

Behavioral coverage is in `tests/unit/test_enrichment_route.py`: pending versus
seen/disabled first summaries, bound and unbound sweep rows, leased bindings,
backfill and effects. The owning contract is
[fresh enrichment queue capacity](../../listen_pusher_pipeline.mdx#fresh-enrichment-queue-capacity).
