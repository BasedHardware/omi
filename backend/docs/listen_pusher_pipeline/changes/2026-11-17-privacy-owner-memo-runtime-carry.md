# Preserve the admitted privacy owner-memo configuration

A normal Cloud Run train could restore shadow reads and the old decision cache
because the runtime source still preceded the admitted O2b configuration.
The prod overlay now carries enforcement 100, shadow 0 and decision cache 0 on
backend, sync and integration, retaining negative-cache/TTL60 at 0 and every
unrelated map entry. Backfill keeps enforcement 0/shadow 10 and now durably
preserves its already-admitted decision-cache OFF state. No worker/GKE/dev/job
scope is added; the offline worker comparison retains its separate privacy
settings instead of inheriting the API admission. Staging explicitly preserves
its previous four maps (enforcement 0/shadow 10/decision cache 100). The staging
check requires those exact retained values and strict equality to prod for
every other JSON key; it does not allowlist the entire environment variable.

The margin lead owns rollout order, qualification and cost measurement; Release
alone applies or rolls back. Its inverse is enforcement 0/shadow 10 using the
current map/artifact, or the existing privacy kill switch. Reconcile source after
an inverse before another train. Both derived manifests come from their owning
generators. There is no source-only activation, fresh guard/window acceptance,
writer-coverage claim or quantified savings claim from this carry.
