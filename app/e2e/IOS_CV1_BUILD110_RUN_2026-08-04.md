# iOS CV1 build-110 physical run — 2026-08-04

Status: bounded physical pass on a composite qualification build. This is not
evidence that this PR head by itself contains every native iOS commit in the
composite; the serialized/session-bound GATT layer remains separately reviewed
in #10573.

## Configuration

- firmware: CV1 `3.0.30+110`
- firmware ZIP SHA-256:
  `8ad0dad061fe637b922d5ed6667a4ac0713ebbe9539fa03ab0744b45e0dcabec`
- composite IPA SHA-256:
  `2ddaf0e3c63a6cf49f0630d9fa5858ca1306056aaa0a58d255f9f5f14b94db8f`
- isolated iOS bundle: `com.omi.reliability.alexsmacbookpro`
- authenticated customer plane: production Firebase plus
  `https://api.omi.me/`
- historical sync authority: explicit Sync tap

The production App Store Omi app was removed from this dedicated test phone
after the user authorized it. The postflight inventory used
`devicectl ... apps --include-all-apps` and proved Omi Dev was the only Omi
bundle. The `--include-all-apps` flag is required: the default inventory lists
developer apps and previously hid the App Store BLE owner.

## Cold reconnect and no-touch preview

1. The previous app process was stopped.
2. The user power-cycled the pendant.
3. The exact composite IPA was cold-launched.
4. Home was left untouched; Listening was never opened.
5. TTS marker `Uniform` ended at `2026-08-04T19:50:00Z`.
6. The home preview contained marker text at the +5-second screenshot and
   remained populated at +15 seconds.

Result: pass. A card tap is not required to publish preview text after the
tested cold app plus pendant reconnect.

The five-second observation is **not** launch-to-first-text latency. It is the
time from the end of a controlled marker to the first scheduled screenshot.
Ambient speech may have warmed the session. Future latency work must timestamp
app launch, BLE connect, GATT ready, ring-tail ready, durable audio, socket
ready, first transcript, and preview paint separately.

## Explicit historical drain while live

The Sync page showed 560 recordings and 196 MB used (42%). Sync was started by
an explicit tap. While upload remained active, the tester returned Home and
spoke TTS marker `Victor`.

- preview contained Victor marker text at the +5-second checkpoint;
- the app remained responsive;
- no BLE disconnect or preview interruption was observed;
- pendant storage decreased to 195 MB / 41% during the controlled window;
- the recording count became 561 because new live capture continued;
- the user later observed 188 MB used, corroborating continued drain.

Result: pass for live-preview priority during one user-authorized historical
drain. The complete backlog and post-drain semantic state have not yet been
audited.

## Open items

- compare canonical source coverage with historical archive manifests after
  drain to exclude duplicate binding;
- verify process-death audio is bound into the original conversation rather
  than merely retained as durable unbound WALs;
- investigate any repeatable whole-app freeze with a timeline/main-thread
  sample;
- measure cold first-preview phase latency and battery/thermal impact;
- repeat Android parity on the same final artifact.

The independent Kimi follow-up classified the process-death owner defect and
the final-pass nits as app-side. It recommended proceeding with this bounded
gate and stopping if a freeze interrupted sync or preview. No freeze occurred
in this run.
