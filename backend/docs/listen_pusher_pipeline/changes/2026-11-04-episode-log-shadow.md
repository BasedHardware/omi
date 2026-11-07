# Episode log shadow drain

Episode legacy mutations now append sealed, content-free facts after commit
in a separate best-effort transaction under the user. Capture failures never
abort the serving write. Facts expire after one day under the reviewed TTL policy.
The sync/finalize log hook marks dirty only; a per-user epoch lease, deadline
Cloud Task and the existing sync sweep publish separate episode/Home views.
Live recording and paid composition retain their existing authorities.

`EPISODES_LOG_ENABLED` and `EPISODES_HOME_ROWS_ENABLED` default on with kill
switches (capture honors the remote flag with env fallback); `EPISODES_LOG_READ_PERCENT` defaults zero and ramps through the Omi
flag store without deploys. Conditional Home reads add an opaque version/ETag
and 304 response. Existing clients remain compatible. See the [runbook](../../runbooks/episode-log.md)
for train order, automatic-state deadlines, drift gates and cost limitations.

The flag defaults and serving contract are owned by [Episode log shadow contract](../../listen_pusher_pipeline.mdx#episode-log-shadow-contract).
