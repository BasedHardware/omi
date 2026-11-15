# Quality push review corrections

Pusher's pending-seal retry bound now has a default-on deploy binding in both
runtime overlays and pusher charts. These bindings preserve the default-on
behavior and make rollback through deployment configuration possible. The
cohost gate records this process-specific owner and rejects a missing binding.

The repair CronJob and continuous worker share `recordSealRepair.freshEnabled`.
Setting it false now reaches both parents and their repair children. No worker
image, enablement, capacity, producer proof or custody policy changes here.

Home's effective deadline parses the server pending clock (or recovers it from
the old deadline), so offline capture age never shortens a newly admitted wait.
Creation is the fallback only without either pending stamp. A new upload revision
may re-stamp a new 24h wait; reads and ordinary retries cannot renew it. Disabling the
Home queue hold restores the original finished_at-only unstamped fallback.
Regression tests cover both clock cases and rendered on/off repair settings.
