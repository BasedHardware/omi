# AAC Decode Failures — typed failures, not silent native noise

Date: 2026-09-01 · Scope: `utils/aac.py` (`AACDecoder.decode`) ·
Guard tests: `tests/unit/test_aac_decode_failure_reporting.py`

## What happened

The GCP prod error feed (backend-listen) carried a family of
`ERROR:libav.aac:*` signatures continuously across 2026-08-30/31 —
combined ~130 events / 30 min at peaks:

```
ERROR:libav.aac:Channel element 1.7 is not allocated        (×12–17 / 30 min)
ERROR:libav.aac:Reserved bit set.                           (×6–11 / 30 min)
ERROR:libav.aac:Error decoding AAC frame header.            (×3–14 / 30 min)
ERROR:libav.aac:Number of bands (…) exceeds limit (…)       (×11 / 30 min)
ERROR:libav.aac:Number of scalefactor bands in group (…) …  (×5 / 30 min)
```

These are FFmpeg's **native codec diagnostics** for a frame its AAC decoder
rejected, emitted while `AACDecoder.decode` held the frame. Reproduced
locally against the pinned PyAV 12.0.0 by feeding the real decoder
payload-scrambled and truncated ADTS frames: every corrupt shape raises
`av.InvalidDataError`/`av.UndefinedError` **and** emits the corresponding
native `libav.aac` line — the prod signatures are our decode loop rejecting
corrupt/truncated client audio, frame after frame.

## What was broken

`AACDecoder.decode` caught `(EOFError, av.AVError)` and returned `b''`. Two
consequences, one contract violation:

1. **The receiver's decode-failure contract never fired for AAC.** The
   listen receiver (`routers/listen/receiver.py`) already owns undecodable-
   frame reporting: `_record_decode_failure` logs a per-frame warning with
   the codec's own message, payload size, and streak, and the one-shot
   `record_fallback(component='silent_mic', …, outcome='exhausted')` at 50
   consecutive drops (1 s at the omi 20 ms frame cadence) — the contract
   #11732 established when opus streams were dropping silently. All of it
   hangs off the decoder *raising*. opuslib raises `OpusError`; the AAC
   decoder swallowed, so a fully undecodable AAC stream recorded a whole
   session with no transcript, no ring buffer, no mixed audio, and **no
   fallback metric** — a fail-open branch with no operator signal (the
   fallback-telemetry contract, `docs/agents/fallback-telemetry.md`).
2. **The only trace left was the context-free native line.** FFmpeg's
   `ERROR:libav.aac:…` carries no uid, session, codec name, payload size, or
   streak — strictly less information than the warning the receiver would
   have logged — and it duplicated that warning per frame once the receiver
   path existed, polluting the error feed the Loop S sensor watches.

## The fix

- `AACDecoder.decode` now **raises `AACDecodeError`** (message = the FFmpeg
  error verbatim, cause = the original `av.AVError`) for frames the codec
  rejects, and still returns `b''` only for benign no-output input (empty
  payload, encoder priming). The receiver's existing `except Exception →
  _record_decode_failure('aac', …)` handles the rest — no receiver change.
- `NativeDuplicateSuppressionFilter` on the `libav.aac` logger drops
  FFmpeg's re-report **only while our own decode call is on the stack**
  (thread-local flag, set/cleared in `finally`); every other `av` consumer's
  native errors still flow.

## Operator-visible after this lands

- Per corrupt frame: `WARNING … Listen audio frame decode failed codec=aac
  type=AACDecodeError bytes=N streak=M detail=<ffmpeg message>` (uid/session
  context via the existing warning shape).
- A fully undecodable stream: one `silent_mic` fallback metric per session —
  the alertable signal that was missing.
- The `ERROR:libav.aac:*` family should disappear from the error feed; any
  residual native lines would indicate a decode outside this module (speech
  profiles, transcode), which keeps its own context.

## Regression coverage

`tests/unit/test_aac_decode_failure_reporting.py` drives the real
`AACDecoder` over real ADTS frames encoded in-process (real PyAV encoder →
real codec context) and the real `ListenReceiver.receive_data` loop; only
the websocket transport is scripted. Covers: corrupt/truncated frames raise
the typed error with FFmpeg detail (mono and stereo, header-only fragments);
clean frames decode; recovery after a corrupt frame and after a burst;
native duplicate suppressed inside our decode window with a negative control
proving the suppression is not vacuous; window-scope (an unrelated native
error right after still logs) and thread-locality; receiver streak
progression, warning shape, one-shot silent-mic fallback at the threshold,
streak reset on recovery, interleaved corrupt/clean streams, and the
`initialize_decoders` production wiring.

Failure-Class: FC-typed-failure-collapsed-to-generic — instance fix; the
class was canonized by #11487 (proactive lane) and applied at the live-STT
boundary by #11732 (opus): a codec that already produces a typed failure
must not have it collapsed into silence by the caller. Here the collapse
happened one layer lower — the decoder itself swallowing `AVError` — so the
receiver's whole reporting contract (built for exactly this failure shape)
never engaged for AAC.
