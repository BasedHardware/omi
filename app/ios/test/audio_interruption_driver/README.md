# Real iOS audio interruption stimulus

**Experimental stimulus; no physical interruption acceptance.** The local
CallKit attempts did not establish an interruption. Use this driver's status and
the separate microphone interruption/recovery oracle together; an attempted
call or Siri action alone is insufficient. See
[the agent guide](../../../../scripts/dev-harness/IPHONE_HARNESS.md).

This separate offline app has three bounded stimuli: default playback of
generated silence, or `--capture` for competing microphone ownership with
all input buffers discarded; or `--local-call` for a synthetic local CallKit
audio lifecycle. Playback and capture deactivate with
`notifyOthersOnDeactivation`. It records session events, never microphone
audio. Use only during an explicitly authorized phone-test session: activation
can interrupt whatever audio app is currently active.

Build with:

```bash
python3 app/ios/test/audio_interruption_driver/build.py \
  --output <fresh-external-directory> --profile <authorized-development-profile> \
  --identity <authorized-signing-identity>
```

`--check` compiles without signing.
The microphone probe's compile check also compiles this driver.

Install `OmiAudioInterruption.app` with `devicectl`. Start a microphone probe
run long enough for baseline and recovery, then launch
`com.friend-app-with-wearable.ios12.development.interruptiondriver`, optionally
with `--capture` (requires this driver's separate microphone grant). After the
five-second playback finishes, bring the microphone probe to the foreground
without terminating it. Collect each app's own Documents directory.

Driver `interruption.json` must show playback/capture start and successful session
deactivation. That is stimulus evidence only: the microphone trace must
independently show real interruption and renewed frame delivery, validated by
its interruption analyzer. Driver launch alone is not acceptance. The driver
overwrites its own one-run receipt, so collect it before another launch.

The production microphone session mixes with other audio. The iOS 27 playback, competing-capture, and separate Siri text-activation
experiments did not produce a microphone interruption; its trace is coexistence
evidence, not interruption recovery. Neither mode is assumed to interrupt:
require actual interruption events in the independently collected mic trace.

This measures competing-app audio behavior, not cellular calls, Siri,
Bluetooth route changes, or every iOS interruption reason. Preserve the signed
app, build manifest, and command receipts outside Git. Remove only these
separate diagnostic apps when the authorized session is finished.

## Synthetic local CallKit stimulus

Launch the same separate bundle with **only** `--local-call`. This creates a
CallKit provider labeled **Omi Local Test**, a generic `omi-local-test` handle,
and `includesCallsInRecents=false`. There is no phone number, contact, remote
participant, SIP stack, PushKit registration, network client, or external call.
It refuses to start if any call is already active or this helper lacks its
previously granted microphone permission.

The provider handles a `CXStartCallAction`, configures `playAndRecord/voiceChat`,
fulfills the start action, and reports its local connection. It never activates
the session directly: only CallKit's `didActivate` callback establishes OS audio
ownership. Five seconds after that callback, it requests `CXEndCallAction`,
fulfills the end, and waits for `didDeactivate`. A ten-second deadline from
start request reports this provider's own UUID ended and invalidates the
provider if any step fails or stalls. A short background task allows cleanup
if the test's system call UI backgrounds the helper. No samples are recorded.

Copy `Documents/interruption.json` before another launch, then check it against
the actual signed build's embedded manifest:

```bash
python3 app/ios/test/audio_interruption_driver/analyze.py /evidence/interruption.json \
  --build /artifact/OmiAudioInterruption.app/build.json
```

A passing stimulus receipt requires observed CallKit activation, at least
4.9 seconds before end request, end-action fulfillment, OS deactivation, and
bounded completion. Permission refusal, rejected transactions, reset, missing
activation/deactivation, timeout cleanup, and partial receipts never pass.
The analyzer always reports `microphone_interruption_qualified=false`; use the
independent microphone analyzer with `--require interruption_recovery` for that
claim. Local CallKit is neither a cellular-call test nor proof that all call
interruption paths work. If iOS declines the synthetic call or still permits
coexisting capture, retain the failure/non-interruption evidence as such.

`build.py --check` compiles with the actual iPhone SDK and runs the hermetic
driver-evidence mutation tests. It never installs or initiates a call.

The same metadata mutation suite also runs in the cross-platform harness lane
via `app/ios/test/audio_interruption_driver/test_driver.py`. It imports no
UIKit/CallKit and invokes no hardware; it rejects incomplete activation, missing
deactivation, timeouts, stale builds, and short/reordered calls. Native SDK
compilation remains a distinct macOS check. A passing synthetic fixture is
never a retained physical trace.

The local CallKit helper declares both `audio` and `voip` background modes.
This is an Info.plist declaration; it adds no PushKit registration, network
transport, external calling capability, or private signing entitlement. The
first physical local-call attempt without `voip` failed its start transaction
with numeric code 1 and never activated audio. The SDK's transaction-error enum
names code 1 `Unentitled`, but that receipt lacked the NSError domain, so the
missing mode alone was not established as the cause.
New failures record only error domain/code, never localized descriptions.

The v4 physical retry reached CallKit but was rejected before its start-action
delegate, with domain `com.apple.CallKit.error.requesttransaction`, code 7
(`MaximumCallGroupsReached`). Its analyzer exits **1**; a following shell
command such as `cat` can mask that exit status unless checked separately.
No audio activation occurred and this failed stimulus cannot qualify recovery.

The current driver waits for `providerDidBegin` before requesting its single
start action. The iPhone SDK documents that callback as the point at which
the provider is fully created and ready to send actions. The earlier immediate
request violated that boundary; the subsequent v5 retry recorded no provider-readiness
callback within its ten-second window and established no interruption. Receipts now include provider readiness, configured group limits and
a count of active calls (no call identities). Limits remain one call/group;
the driver refuses an existing call rather than increasing limits. Generic
handle support is explicit both in configuration and the action.

The CLI regression suite checks actual subprocess exit codes: 0 only for
complete stimulus evidence, 1 for completed failures, and 2 for incomplete
or mismatched-build evidence. It includes the reduced code-7 failure sequence.
