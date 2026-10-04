# Modulate streaming protocol guard

`MODULATE_STREAM_PROTOCOL_GUARD_ENABLED=true` enables the guarded adapter. It is
**off by default**, pinned when each socket is constructed, and requires public
multilingual qualification before production enablement. Roll back by setting
it to `false`; new sockets use the original adapter. This change enables no
deployment and changes no endpoint, routing order, keepalive or replay policy.

The [vendor streaming contract](https://docs.modulate.ai/api-reference/stt/streaming)
allows nullable partial timing and speaker metadata. Its partial example and
field list omit `utterance_uuid`, while finals carry it. The old
adapter held one preview, cleared it on any final, and divided nullable timing
by 1000 during terminal flush. A null-timed preview followed by a server error
erased its typed cause and left the completion event unset; followed by `done`,
it turned successful completion into a generic socket death.

The guard retains at most 64 pending previews, correlates updates/finals by
UUID when present, and retains the last known timestamp/speaker only when that
UUID proves the association. UUID-less partials supersede a single anonymous
preview. Every final retires that anonymous preview, even if its time/text
differs, to prevent terminal emission of already-finalized text. An interleaved
final can therefore discard an unfinished UUID-less preview; selective
retirement requires an identity the documented partial shape does not supply.
Null-timed UUID-less updates do not inherit an unproven timestamp.
Empty previews retract prior text. Finals pass through even when their preview
was evicted. At termination, timed previews emit once in
capture order; text with no proven timestamp is not assigned an invented
capture anchor. Such a preview produces a content-free warning. The inherited
1 ms tail interval is a persistence representation, not a measured duration.
Unfinalized preview quality and speaker attribution still need qualification.

An error's death latch and completion event are published before flushing any
tail, so local callback errors cannot erase vendor evidence. The guard also
maps the documented insufficient-credit, concurrency and authorization error
messages to existing bounded budget/rate/auth reasons. Invalid audio retains
the session-scoped `other` death reason, while the stream-close counter records
`provider_invalid_request` instead of claiming a transport failure. Unknown
messages retain the legacy generic classification.

`omi_stt_stream_close_total` counts Modulate terminal **error frames**, not all
WebSocket closes or completed sessions. Normal `done` does not increment it.
Use serving settlements by cause, fallback outcomes, connect outcomes and
client terminal failures together; these are overlapping observations and
must not be summed into a unique-session disruption rate.

Verification:

```sh
printf '%s\n' tests/unit/test_modulate_protocol_guard.py > .local/modulate-tests.txt
BACKEND_UNIT_TEST_FILE_LIST="$PWD/.local/modulate-tests.txt" backend/test.sh
```

The suite replays documented frames through the real receive loop, tests
interleaved final/preview correlation, terminal callback failure, bounded
storage and flag-off rollback. It uses no vendor credentials or customer data.
