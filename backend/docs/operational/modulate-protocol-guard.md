# Modulate streaming protocol guard

`MODULATE_STREAM_PROTOCOL_GUARD_ENABLED=true` enables two adapter fixes. It is
**off by default** and pinned when each socket is constructed. Roll back by
setting it to `false`; new sockets retain the original adapter behavior,
including its nullable-timing failure. Public multilingual qualification is
still required before production enablement.

1. Terminal preview flush treats a null `start_ms` as zero, matching the legacy
   default for a missing timestamp, instead of dividing `None` by 1000. This
   prevents a null-timed tail from erasing a vendor error's typed cause or
   turning normal `done` into a generic socket death. The inherited 1 ms tail
   interval and zero default are persistence representations, not measured
   speech timing.
2. UUID-bearing partials are tracked by `utterance_uuid`. Updates retain the
   last known timestamp and speaker for the same UUID. A final retires only
   the matching identified preview; unrelated identified previews remain
   pending. Empty identified updates retract their own preview. There is no
   capacity eviction. Terminal flush emits remaining identified previews
   once in timestamp order, retaining the existing preroll filter. A UUID
   without a known timestamp uses the same zero default.

UUID-less partials use exactly the legacy single-preview path, apart from the
flagged nullable-timing fix. A nonempty partial replaces that preview; an empty
partial leaves it unchanged. **Any nonempty final clears the anonymous preview,
even if it belongs to different speech.** Empty finals leave it pending.
Anonymous terminal tails retain legacy `SPEAKER_00`, whitespace handling,
preroll filtering and the 1 ms interval. UUID-bearing partials do not overwrite
this anonymous slot. There is no text matching, inferred identity, anonymous
preview cache or anonymous eviction.

The remaining legacy limitation is intentional: a UUID-less preview has no
identity, so the adapter cannot guarantee both retaining all pending speech
and attributing it to the correct final. This PR makes no such guarantee and
changes no error classification, terminal callback ordering, endpoint,
routing, keepalive or replay policy. Callback failures retain legacy behavior.
No flag is enabled by a deployment change in this PR.

Verification:

```sh
printf '%s\n' tests/unit/test_modulate_protocol_guard.py > .local/modulate-tests.txt
BACKEND_UNIT_TEST_FILE_LIST="$PWD/.local/modulate-tests.txt" bash backend/test.sh
```

The suite exercises the production receive loop for done/error, nullable tails,
UUID interleaving, anonymous legacy behavior, mixed streams, more than 64
pending previews and flag-off rollback. It uses no vendor credentials or
customer data.
