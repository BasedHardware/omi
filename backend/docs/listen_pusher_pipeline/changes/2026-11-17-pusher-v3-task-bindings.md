SCA-2792 supplies the production pusher with `SYNC_TASKS_PROJECT=based-hardware`
and `SYNC_TASKS_LOCATION=us-central1`, matching listen. Both the runtime overlay
and the pusher Helm values declare the bindings; the composed manifest is regenerated.
This repairs the incomplete Cloud Tasks configuration used by the v3 capture-end
trigger. It does not establish summary recovery; SCA-2791 owns the builder repair.

Release owns the pusher-only configuration rollout, retaining the currently
served immutable image, all other environment entries, and the beta v3 gate.
Queue existence remains unknown after the read-only permission denial; an
authorized existence receipt for `conversations-v3` in `based-hardware/us-central1`
is required before rollout. Do not create or reconfigure the queue.

Rollback removes only these two entries from the production overlay and Helm
values, then regenerates the manifest. Release must server-dry-run both directions
and admit the exact pusher-only delta before applying either direction.
