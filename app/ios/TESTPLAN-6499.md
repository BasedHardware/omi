# TESTPLAN — iOS phone-mic interruption fix (issue #6499)

On-device validation plan for PR #6565. Units cover the state-machine
behaviour in `capture_provider_test.dart`; the four scenarios below cover what
unit tests cannot: the actual native `AVAudioSession` interruption flow,
`flutter_sound` engine resume, and the UI state transitions end-to-end.

## Prerequisites

- iPhone running iOS 18+, SIM with a working phone number.
- A second phone to place the inbound call (or Siri "call me back in 10
  seconds" from a second number).
- Omi dev build installed via `flutter run --flavor dev` or TestFlight dev
  build that contains commits on branch `caleb/6499-ios-audio-interruption`.
- Signed into an Omi dev account with mic permission already granted.
- **No Omi hardware device paired** — this plan exercises the phone-mic path
  only; device recording is a separate lane and unaffected.

## How to read each scenario

Each scenario lists:

- **Steps** — exact taps, wait times, and the call action.
- **Expected** — what the UI and transcript should do if the fix works.
- **Fail signals** — what it looks like if a regression has slipped in.

For each scenario, paste the observed outcome back into PR #6565 as a
comment: `Scenario N: PASS` or `Scenario N: FAIL — <symptoms>`.

---

## Scenario 1 — Call received mid-recording (decline)

**Steps**

1. Open the app, start phone-mic recording from the home bottom-nav record
   button. Wait ~10 s and speak a recognisable phrase ("marker alpha") so the
   transcript has content.
2. From the second phone, place a call to the test device.
3. Decline the incoming call.
4. Speak another recognisable phrase ("marker beta") for ~10 s.
5. Stop recording. Open the resulting conversation transcript.

**Expected**

- While the call is ringing, the bottom-nav button turns **orange** (amber);
  Dynamic Island mic indicator disappears (iOS-controlled).
- After decline, the button returns to **red** within ~1 s and "marker beta"
  lands in the transcript.
- Transcript contains both "marker alpha" and "marker beta" with no gap
  longer than ~1 s between them.

**Fail signals**

- Button stays red throughout — UI is lying (regression of gap B).
- Button stays orange after call ends — restart did not fire (regression of
  gap A `.ended` observer or the 250 ms delay re-check).
- Transcript cut off at "marker alpha" with no "marker beta" — native engine
  never resumed.

---

## Scenario 2 — Call received mid-recording (accept + hang up)

**Steps**

1. Start phone-mic recording. Speak "marker gamma" for ~10 s.
2. From the second phone, place a call. **Accept** it on the test device.
3. Hold the call open for ~10 s, then hang up from the test device.
4. Speak "marker delta" for ~10 s.
5. Stop recording.

**Expected**

- Button turns orange while on the call.
- After hang-up, button returns to red within ~1 s.
- Transcript contains "marker gamma" and "marker delta". The call window
  itself will be absent from the transcript (iOS mutes the mic) — that is
  expected; the fix is about resuming after.

**Fail signals**

- Button stuck orange after hang-up.
- "marker delta" missing from the transcript.
- App crashes on call end.

---

## Scenario 3 — Cold start into an active call (stall heartbeat)

This covers the edge case the `AVAudioSession.interruptionNotification`
observer alone would miss: the app starts recording when the interruption
was already in progress, so no `.began` event ever fires.

**Steps**

1. With the app backgrounded/closed, initiate a call **first** (outgoing or
   incoming, either works — the audio session just needs to be owned by
   Phone).
2. While on the call, foreground the Omi app and tap the record button.
3. Speak "marker epsilon" and wait ~5 s (longer than the 3 s stall
   threshold).
4. Hang up the call.
5. Speak "marker zeta" for ~10 s.
6. Stop recording.

**Expected**

- When the record button is tapped during the call, it briefly shows the
  initialising spinner, then flips to **orange** within ~3 s (the stall
  heartbeat detecting no bytes from the muted session).
- After hang-up, button flips back to **red** within ~1 s and "marker zeta"
  lands in the transcript.
- "marker epsilon" may or may not land depending on iOS; the critical
  signal is that the button reflects the stalled state rather than lying.

**Fail signals**

- Button stays red (or initialising spinner) the entire time on the call —
  the stall heartbeat did not fire (regression of gap C).
- No transitions at all after hang-up.
- "marker zeta" missing.

---

## Scenario 4 — User stops during the 250 ms restart window

This exercises the race guard (commit `718538d40`): the user taps stop in
the brief window between the mic being released and the fresh
`streamRecording()` call.

**Steps**

1. Start phone-mic recording. Speak for ~10 s.
2. Trigger a call interruption (easiest: have the second phone call and
   decline fast) — the button should flip to orange.
3. The instant the button flips back from orange toward red (the restart
   is firing), **tap the record button to stop**. You have ~250 ms; it is
   tight but doable with practice.
4. Observe.

**Expected**

- Recording ends. Button returns to the purple/mic (idle) state.
- Transcript processes and closes normally.
- App does **not** spontaneously restart recording a moment later.

**Fail signals**

- Recording restarts by itself after the user-tapped stop. That means the
  post-delay state re-check is missing or broken.
- Button gets stuck in an intermediate state.

> Note: the window is small. If you miss it once, repeat. If you cannot
> reliably hit the window after 3 tries, note that as "could not reproduce
> race" — the guard is still in the code and is covered by inspection.

---

## Regression check — Omi hardware device recording

Paired-device recording uses a different lane (`deviceRecord`, BLE audio).
None of the changes on this branch touch that path, so this is just a
sanity check that I did not break the other recording mode.

**Steps**

1. Pair the Omi hardware device.
2. Start a device recording from the paired UI.
3. Speak for ~10 s, stop.

**Expected**

- Button behaviour and transcript are identical to `main`: red during
  record, purple when stopped.
- No orange button anywhere (the `interrupted` state is phone-mic only).

**Fail signals**

- Any amber/orange state during device recording.
- Transcript truncation.

---

## What to paste into the PR when done

```
On-device results for #6565 (device: <iPhone model / iOS version>, build:
<flavour + commit sha>):

Scenario 1 (call + decline): PASS / FAIL — <details>
Scenario 2 (call + accept + hang up): PASS / FAIL — <details>
Scenario 3 (cold start into active call): PASS / FAIL — <details>
Scenario 4 (user stop during restart): PASS / FAIL — <details>
Regression check (device recording): PASS / FAIL — <details>
```

Attach a screen-recording for any FAIL. Logs from `flutter logs` or Xcode
console filtered by `CaptureProvider` / `AudioInterruptionManager` help
diagnose regressions without needing a debugger session.
