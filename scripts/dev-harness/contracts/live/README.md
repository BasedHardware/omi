# Live-session wire

[Protocol and lifecycle](../../LIVE_SESSIONS.md). The request/response schema
is for the private Unix socket, not Flutter's array-framed daemon stream.
`params` is validated by operation: controls has method+string-valued params;
logs has optional nonnegative cursor and limit 1..1000; verify has a nonempty
selected journey list; every other operation takes an empty object. Unknown
params fail closed. Server assigns artifact paths; clients cannot pick them.

Error codes: busy, stale-session, unsafe-config, unsupported-operation,
daemon-died, deadline, protocol-error, unready, stale-build. They map to blocked
(exit 2). Flutter nonzero restart code is rejected (1), not protocol success.
