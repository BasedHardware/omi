# SwiftUI and AppKit scroll debugging

Use this playbook when a macOS scroll surface jumps, sticks, stops tracking,
returns to an edge, or behaves differently during fast input. It is especially
important for SwiftUI content hosted by AppKit, heterogeneous rich content, and
nested scroll views.

The governing product contract for chat is
[`INV-CHAT-2`](../../../docs/product/invariants/chat-scroll-placement.md).
This guide explains how to diagnose a violation; the invariant and its guard
tests remain the authority for product behavior.

## Start with the three authorities

Every unexplained viewport movement comes from one of three classes. Do not
change timers or follow-state policy until evidence identifies the class.

| Authority | Question | Evidence |
|---|---|---|
| Intent | Did application code request movement? | Log every `scrollTo`, clip-view mutation, restore, and follow transition with a reason. |
| Input routing | Which native scroll view received the event? | Event phase, deltas, window, hit-tested view, nested scroll view, and resolved owner. |
| Geometry | Did the coordinate system change under the reader? | Scroll top, viewport height, document height, and visible anchor before and after each delivered sample. |

A state machine can correctly report that the reader owns the viewport while
SwiftUI changes the document height and AppKit preserves the wrong visual
anchor. Conversely, stable geometry cannot help if a nested horizontal scroll
view consumes vertical wheel input. Test all three authorities independently.

## Minimum diagnostic trace

Add temporary, non-production instrumentation through Omi's file logger. Do
not use `print`: named app launches do not reliably capture standard output.
Obtain the exact log path from the running bundle with
`./scripts/omi-ctl log-path`.

Record these bounded values for each relevant transition:

- monotonic timestamp and gesture phase;
- input deltas and the native scroll-view identity;
- top-based scroll offset;
- viewport and document heights;
- whether the position is at the live edge;
- reader/follow ownership mode;
- every programmatic movement and its reason;
- content count or stable layout generation, never message text.

Use one searchable prefix, such as `SCROLL_TRACE`. Never log prompts, rendered
message content, window titles, credentials, or other user data. Remove
temporary high-volume telemetry before committing unless it is deliberately
gated and reviewed as a permanent diagnostic surface.

## Classify the first impossible transition

Reproduce once, then inspect the first sample that contradicts the reader's
motion. Later samples are usually consequences.

### Programmatic movement

The viewport changes immediately after a logged `scrollTo`, restore, or native
clip mutation.

- Find the competing authority instead of adding another suppression boolean.
- Separate initial presentation, explicit user sends, remote content arrival,
  conversation changes, and reader-selected navigation.
- Pending launch or streaming work must be cancelable when reader input wins.
- A new presentation may start at the live edge; an existing presentation must
  preserve explicit reader position.

### Input-routing failure

Wheel events continue, but the transcript position stops changing or a nested
view moves instead.

- Resolve the enclosing `NSScrollView` from the mounted hierarchy rather than
  assuming SwiftUI's structure.
- Check vertical versus horizontal dominance before forwarding nested events.
- Include trackpad phases and momentum; a wall-clock timer is not authoritative
  when AppKit provides live-scroll start and end notifications.
- Verify SwiftUI has not replaced the native scroll view while an observer is
  still attached to the old instance.

### Geometry mutation

No programmatic movement fires, input ownership remains with the reader, and
the document height changes sharply while the viewport jumps.

- Treat the document-height change as the primary failure.
- `LazyVStack` is not behaviorally transparent for rich rows whose off-screen
  heights are estimates. Markdown tables, fenced code, images, selectable text,
  and AppKit-backed views can materialize with very different real heights.
- Prefer eager measurement for an already bounded transcript window.
- If eager measurement is too expensive, optimize with measured-height caches
  or explicit anchor compensation and retain the stable-document test. Do not
  restore estimated virtualization without equivalent evidence.

## Build a representative regression

Policy-only tests cannot catch framework negotiation between SwiftUI and
AppKit. Mount the production view in `NSHostingView`, discover its real
`NSScrollView`, drive the native input path, and inspect native geometry.

For transcript scrolling, extend
`Desktop/Tests/ChatTranscriptGestureHarnessTests.swift`. A regression should:

1. Present enough content to exceed several viewports.
2. Settle the intentional initial placement.
3. Drive rapid wheel or trackpad-like bursts through the mounted event path.
4. Exercise the competing condition: streaming, nested scrolling, view
   replacement, or heterogeneous row materialization.
5. Assert the reader's native viewport position and document geometry, not only
   Swift state.
6. Repeat the interaction enough times to cross lazy-layout and momentum
   boundaries without relying on an arbitrary sleep as the assertion.

Fixtures should include varied row heights and, where relevant, long Markdown,
tables, fenced code blocks, nested horizontal scrolling, timestamps, and rich
AppKit-backed content. Uniform short rows can hide the production failure.

Run the focused mounted suite from `desktop/macos`:

```bash
xcrun swift test --package-path Desktop --filter ChatTranscriptGestureHarnessTests
```

Then run the test-quality and formatting checks required by
[`desktop/macos/AGENTS.md`](../AGENTS.md), rebuild a uniquely named bundle, and
exercise the exact user-facing gesture:

```bash
OMI_APP_NAME="omi-scroll-debug" ./run.sh --yolo --no-wait
```

## Review checklist

Before calling a scroll fix complete, confirm:

- a fresh presentation still opens where product policy requires;
- explicit reader movement wins immediately and survives content updates;
- fast input and momentum do not create a timer-sized ownership gap;
- nested scroll views keep their intended axis without swallowing the other;
- the native document height remains stable while traversing loaded content;
- the prompt rail or custom indicator tracks the final native position;
- deliberate return to the live edge resumes following;
- no temporary content-bearing or high-volume telemetry remains;
- a named bundle was exercised, not only compiled.

## Incident that established this playbook

PR [#11035](https://github.com/BasedHardware/omi/pull/11035) fixed several
independent chat-scroll failures. The final stuck/jump symptom persisted after
input ownership and nested event routing improved. Runtime telemetry showed no
programmatic bottom scroll; instead, SwiftUI changed the transcript document
height from roughly 32,900 to 57,600 points in one frame during an upward
gesture and AppKit moved the viewport from roughly 944 to 25,381. Replacing the
bounded transcript's `LazyVStack` with eager measurement stabilized the native
document, and a mounted rapid-traversal test now guards that behavior.

The general lesson is: record intent, event destination, viewport position,
and document dimensions before selecting a fix. A jump must come from requested
movement, misrouted input, or a mutated coordinate system.
