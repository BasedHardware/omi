# Stale Windows list-client refusal

Operational knob for `GET /v1/action-items` only. Classification lives in
`utils/action_items_list_guard.py` and is the same exact-string match used by
the extra hot-loop ceiling: `omi-windows/1.0.0`. An unknown, absent, or
differently-versioned User-Agent is never classified as stale.

## Flag

`ACTION_ITEMS_LIST_STALE_CLIENT_REFUSE`

| Value | Behaviour |
| --- | --- |
| unset, empty, `0`, `off`, `false`, `no`, anything else | current behaviour (serve the list; still subject to the 12/min and extra 4/min ceilings) |
| `1`, `on`, `true`, `yes` | refuse that one build with HTTP 426 |

Read at call time. Flip or revert from config; no code deploy.

## Response

`426 Upgrade Required` with FastAPI `detail`:

```json
{
  "error": "upgrade_required",
  "minimum_supported_build": "omi-windows/1.0.35",
  "message": "This Omi for Windows build is no longer supported for the task list. Update to a current Omi for Windows release to continue seeing your tasks."
}
```

The stale build will not render this. Tasks are not deleted or mutated.

## Metric

`omi_action_items_list_refused_total{client,decision}`

- `client` is the closed classification constant `stale_windows` only — never a raw User-Agent. Unknown values collapse to `other`.
- `decision=allow` while the flag is off (match-set confirmation).
- `decision=refuse` when the request is rejected.
- `decision=other` is a cardinality collapse bucket, not a third product outcome.

Confirm `decision=allow` labels only the stale build before flipping the flag.
After the flip, `decision=refuse` should replace that series at the same rate.

A page cap was examined and rejected on 2026-09-21: that build ignores
`has_more` and would silently truncate user-visible tasks.
