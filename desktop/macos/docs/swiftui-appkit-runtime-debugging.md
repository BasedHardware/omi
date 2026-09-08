# SwiftUI and AppKit runtime debugging

Use this playbook for macOS UI failures whose visible symptom does not reveal
the faulty layer: jumps, stale views, lost input, layout loops, beachballs,
incorrect restoration, behavior that fails only under fast interaction, or
state that appears correct while the rendered app is wrong.

SwiftUI/AppKit failures often cross declarative state, view identity, native
objects, run-loop delivery, and layout. The goal is to locate the first
impossible transition before changing policy. Scroll behavior is the worked
example at the end, not the limit of this method.

## Build the causal map first

Write down the expected chain from product intent to pixels before adding a
fix. For each link, name its authority and observable evidence.

1. **Product authority** — what behavior did the user request, and which owner
   may change it?
2. **State and identity** — which model, generation, session, or presentation
   instance carries that authority?
3. **Delivery** — which callback, notification, event, task, actor, or run-loop
   phase advances it?
4. **Native boundary** — which `NSView`, `NSWindow`, responder, delegate, or
   framework object actually performs the operation?
5. **Layout and rendering** — what geometry or visual output proves that the
   operation took effect?

Do not add another owner, observer, boolean, retry, or timer until this map
shows which link failed. A second authority can hide the symptom while making
future races harder to reason about.

## Trace facts, not theories

Add temporary, non-production instrumentation through Omi's file logger. Do
not use `print`: named app launches do not reliably capture standard output.
Obtain the exact log path from the running bundle with
`./scripts/omi-ctl log-path`.

Use one searchable prefix and record only bounded metadata:

- monotonic sequence or timestamp;
- operation and reason;
- model/session/presentation generation;
- SwiftUI and native-object identity where replacement is possible;
- callback, event phase, actor, or run-loop delivery point;
- compact state before and after the transition;
- native geometry or other rendered outcome;
- content count or shape, never user content.

Never log prompts, rendered messages, window titles, credentials, filesystem
contents, or other user data. Remove temporary high-volume telemetry before
committing unless it is deliberately gated and reviewed as a permanent
diagnostic surface.

Instrumentation should make competing hypotheses produce visibly different
traces. If every hypothesis predicts the same log, collect a more discriminating
fact instead of adding volume.

## Find the first impossible transition

Reproduce once and read the trace chronologically. Stop at the earliest point
where reality differs from the causal map. Later anomalies are usually
consequences.

| Evidence | Likely failure class |
|---|---|
| The wrong state transition occurs | Competing authority, stale callback, incorrect identity, or reducer policy |
| State is correct but the expected callback never arrives | Event routing, lifecycle, cancellation, run-loop mode, or actor delivery |
| Callback arrives on an object that is no longer mounted | Native-object replacement or stale observer/delegate binding |
| State and callbacks are correct but geometry changes unexpectedly | Layout estimation, measurement feedback, or native/declarative coordinate mismatch |
| Geometry is correct but pixels or accessibility remain stale | Rendering invalidation, transaction, representable update, or accessibility projection |
| The main thread stalls | Reentrant state/layout feedback, excessive eager work, selection/layout interaction, or blocking actor work |
| Slow interaction works but bursts fail | Coalescing, momentum/phase handling, task cancellation, stale generations, or backpressure |

Prefer evidence that falsifies an entire class. For example, logging every
programmatic movement plus native geometry distinguishes a policy-driven jump
from a coordinate-system mutation immediately.

## Common cross-layer traps

### Multiple authorities

SwiftUI state, an AppKit delegate, delayed work, and persistence can each appear
to own the same behavior. Choose one lifecycle authority and make other layers
request transitions through it. Delayed work must be cancelable when a newer
generation or explicit user action wins.

### Unstable identity

SwiftUI may recreate a representable or replace its native view while a local
monitor, observer, coordinator, or delegate still references the old object.
Trace both logical identity and native object identity. Rebind deliberately and
prove that stale callbacks cannot mutate the current generation.

### Timers standing in for lifecycle

A delay can make a race less frequent without identifying completion. Prefer
framework lifecycle signals, explicit acknowledgements, or generation-fenced
state transitions. Use a bounded timer only when the platform exposes no
authoritative terminal event, and test the fallback separately.

### Layout as a hidden writer

Layout is not observational when it changes document size, intrinsic content
size, selection overlays, or state read by the same hierarchy. Avoid writing
high-frequency geometry back into parent state that rebuilds unchanged native
content. Treat virtualization and measurement strategy as semantic behavior,
not a transparent performance detail.

### Main-actor and run-loop assumptions

Delivery on the main actor does not guarantee delivery in the run-loop mode
needed during tracking or momentum. Record where and when callbacks execute.
Do not dispatch asynchronously merely to hide reentrancy; if callbacks can
request nested transitions, use an explicit non-reentrant queue or state
machine.

### Partial improvement

If one change makes the bug feel better but does not remove it, preserve that
evidence. It often means multiple independent failure classes overlap. Confirm
what the partial fix changed, then inspect the first remaining impossible
transition instead of repeatedly tuning the same mechanism.

## Reproduce at the real boundary

Pure policy tests are useful but cannot prove framework negotiation. When the
failure crosses SwiftUI and AppKit, mount the production view in
`NSHostingView`, discover the real native hierarchy, drive the native input or
callback path, and inspect the native outcome.

A representative regression should:

1. Exercise the production owner and mounted view, not a source-string proxy.
2. Use realistic identity and lifecycle transitions.
3. Drive the framework boundary that failed: `NSEvent`, notification,
   delegate, responder chain, layout pass, or representable update.
4. Include the competing condition: rapid input, replacement, cancellation,
   streaming, heterogeneous content, or nested callbacks.
5. Assert both authoritative state and native/rendered outcome.
6. Repeat enough transitions to cross scheduling and lifecycle boundaries.
7. Avoid making an arbitrary sleep the assertion; pump a real integration run
   loop only when the framework boundary provides no injectable clock.

Fixtures should be adversarial in the dimension that matters. Uniform short
rows, one presentation identity, one callback, and slow input can all make an
invalid implementation look correct.

## Turn the diagnosis into a durable guard

The final test should encode the product invariant or failure-class boundary,
not the implementation chosen today.

- Assert outcomes such as stable native geometry, current-generation mutation,
  bounded callback depth, or preserved reader authority.
- Keep diagnostic helpers small and reusable when another test can exercise the
  same framework boundary.
- Document why a native mounted test is necessary when a pure state-machine
  test cannot observe the failure.
- Retain a focused test command for iteration, then run the component checks
  required by [`desktop/macos/AGENTS.md`](../AGENTS.md).
- Rebuild a uniquely named bundle and exercise the exact user-facing path; a
  compile or unit test alone is not runtime evidence.

```bash
OMI_APP_NAME="omi-runtime-debug" ./run.sh --yolo --no-wait
```

## Worked example: chat scroll geometry

The governing product contract is
[`INV-CHAT-2`](../../../product/invariants/chat-scroll-placement.md), and
the mounted boundary lives in
`Desktop/Tests/ChatTranscriptGestureHarnessTests.swift`.

PR [#11035](https://github.com/BasedHardware/omi/pull/11035) fixed several
independent chat-scroll failures:

- delayed and streaming work competed with reader ownership;
- a nested horizontal code-block scroll view intercepted vertical input;
- observers had to follow SwiftUI native-scroll-view replacement;
- run-loop and live-scroll lifecycle affected rapid input delivery;
- rich off-screen rows changed the lazy transcript's estimated height.

The last symptom persisted after ownership and event routing improved. A trace
showed no programmatic bottom scroll. Instead, SwiftUI changed the document
height from roughly 32,900 to 57,600 points in one frame during an upward
gesture, and AppKit moved the viewport from roughly 944 to 25,381. The first
impossible transition was therefore geometry mutation, not follow-state policy.

The bounded transcript now uses eager measurement, and the mounted regression
drives repeated fast bursts through 120 messages while asserting that the real
`NSScrollView` document height remains stable. Nested routing and ownership
remain separately guarded because they were independent contributors.

Run that focused suite from `desktop/macos`:

```bash
xcrun swift test --package-path Desktop --filter ChatTranscriptGestureHarnessTests
```

The reusable lesson is broader than scrolling: map authority through native
output, trace the first impossible transition, reproduce at the framework
boundary, and guard the outcome rather than the current implementation.
