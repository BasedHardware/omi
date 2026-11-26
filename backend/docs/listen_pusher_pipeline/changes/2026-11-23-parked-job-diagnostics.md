# Scheduler quarantine diagnostics

SCA-3880 adds bounded evidence to scheduler quarantine records. It distinguishes
lease expiry from typed worker validation and records unknown causes explicitly.
The scheduler records evidence on its existing write. Recovery, retry, and
audio retention continue through their existing paths.

See the [batch quarantine payload contract](../../listen_pusher_pipeline.mdx#deterministic-batch-worker-validation-disposition).
