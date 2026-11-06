# Typed final-pass boundaries

Unit diagnostics now travel in an invocation context rather than attributes
added to arbitrary exceptions. The selected unit, original exception class,
cause and code-owned diagnostic reason remain intact, including revalidation.
Empty projection-part cleanup initializes its temporary references explicitly.

The final-pass result declares its string outcome and optional diagnostics.
The durable metric exporter implements Prometheus's Collector base. The budgeted
read-only SDK snapshot exposes public bind/clear methods on its transaction
subclass; RPC deadlines, disabled SDK retries and cleanup behavior are unchanged.
URI refusal declares its non-returning path, and malformed enrichment tasks
explicitly guard absent payloads. Cross-module dispatch and failure helpers are
public, with in-tree callers migrated together. No type suppressions, policy,
rollout, retention, budget or persistence semantics change.
