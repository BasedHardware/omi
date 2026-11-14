# Quality push review corrections

Pusher's pending-seal retry bound now has a default-on deploy binding in both
runtime overlays and pusher charts. The sync collision-suffix admission switch
is likewise declared on all main-backend cohosts: the four Cloud Run services
and backend-listen. These bindings preserve the default-on behavior and make
rollback through deployment configuration possible.

The repair CronJob and continuous worker share `recordSealRepair.freshEnabled`.
Setting it false now reaches both parents and their repair children. No worker
image, enablement, capacity, producer proof or custody policy changes here.

Home's effective deadline parses each candidate clock before choosing it, so an
ISO capture end cannot lose precedence to a newer pending clock. Disabling the
Home queue hold restores the original finished_at-only unstamped fallback.
Regression tests cover both clock cases and rendered on/off repair settings.
