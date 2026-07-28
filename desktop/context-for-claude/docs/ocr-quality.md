# OCR quality — what is wrong, what to change, how to prove it

`recall` is a full-text search over `frames.ocrText`. A term the recogniser got wrong is not merely
ugly — it is **unfindable**, and the product tells Claude that an empty result inside the coverage
window is evidence something did not happen (`Tools.statusDescription`, `renderStatus`). So a
mis-OCR'd token converts silently into a confident false statement. This is a correctness defect in
the honesty contract, not a cosmetic one.

Everything below was measured on this machine, not reasoned about. Commands to reproduce are at the
end. **The headline finding contradicts the obvious hypothesis** — see [What is *not* the
cause](#what-is-not-the-cause).

Owner file: `Sources/ContextApp/Capture/ScreenWatcher.swift`. This document exists because that file
was being edited concurrently for unrelated reasons (redaction, dedup, self-exclusion); whoever
applies these changes must reconcile with that work.

---

## 1. What is actually wrong

### 1.1 The capture is specified in points, so on every Retina Mac it is a 1x capture

`SCWindow.frame` and `SCContentFilter.contentRect` are in **points**. `SCStreamConfiguration.width`
and `.height` are in **pixels** (SDK header: *"output width as measured in pixels"*). `captureSize`
passes the point size straight through:

```swift
// ScreenPipeline.captureSize — Sources/ContextApp/Capture/ScreenWatcher.swift:489
let scale = min(1, CGFloat(maxPixelSize) / max(frame.width, frame.height))
```

`min(1, …)` can only ever shrink. So a window is captured at, at best, one pixel per point — half the
linear resolution of the backing store on a 2x display — and every glyph reaches Vision at half
height before anything else happens.

Measured on this machine (`NSScreen`):

| display | points | backing scale | native pixels |
|---|---|---|---|
| built-in | 1512 × 982 | 2.0 | 3024 × 1964 |
| external 4K | 1920 × 1080 | 2.0 | 3840 × 2160 |

### 1.2 Worse: on any display wider than 1600 points the app downscales *below* 1x

`maxPixelSize = 1600` clamps the point size too. On the external display a full-screen window is 1920
points wide and is captured at **1600 px** — a 0.83x downscale of content that was already available
at 1x, and 0.42x of what was on the screen. This is the single most damaging setting, and it is the
one the evidence traces back to (§2).

### 1.3 One constant governs two unrelated things

`maxPixelSize` is both the OCR input bound *and* the stored-JPEG bound:

```swift
static let maxPixelSize = 1600                                  // :319
...
let sized = downscaled(image, longestSide: maxPixelSize) ?? image  // writeJPEG, :625
```

Because the capture is already clamped to ≤ 1600, `downscaled` in `writeJPEG` is currently a no-op —
**the stored JPEG width is exactly the OCR input width**. That is what makes the damage measurable
from the database, and it is also why OCR resolution cannot be tuned today without changing storage.

Confirmed against the live database (`~/Library/Application Support/ContextForClaude/context.db`,
942 frames captured 02:23–14:46 on 2026-07-28). Stored JPEG widths, 120 sampled frames:

| width | frames | what it is |
|---|---|---|
| 1512 | 73 | full-screen window, built-in display, captured at 1x |
| 1600 | 5 | full-screen window, external 4K, captured at **0.83x** |
| 723–1200 | 9 | smaller windows, all captured at 1x |

1600 × 900 is exactly `1920 × 0.8333, 1080 × 0.8333`, and 1512 × 949 is exactly the point size — the
requested dimensions come back verbatim, so there is no ambiguity about what Vision was handed.

---

## 2. The evidence, mapped to the cause

| captured | actual | cause |
|---|---|---|
| `sung ten deedie. Respring scron and audio, oven while using other applications` | `Screen & System Audio Recording… even while using other applications` | §1.2 — the below-1x downscale. Measured CER in that configuration: **19.6%**, which is this level of garbage. |
| `ITerm` | `iTerm` | Input size, not language correction. The **only** frame in the database containing `ITerm` is 1600 × 900 — the external display. `iTerm` never appears correctly anywhere. |
| `omi-Q.12.66-test` | `omi-0.12.66-test` | `0`→`Q` is a glyph confusion. In the sweep, recall of this exact needle ranged **1/4 to 4/4 purely as a function of input size**, with language correction held constant. |
| `9d1c250a-61b-…` and `9d1c250a-e61b-…` | one URL, two readings | Output instability at the operating point. UUID needle recall ranged **0/4 to 3/4** across input sizes; see §5.4 for the same instability measured on real frames. |

Two pieces of corroboration from the live database, which are stronger than any fixture:

**The same System Settings pane, read correctly in a 1512 px frame:**

> `Screen & System Audio Recording / Allow the applications below to record the content of your
> screen and audio, even / while using other applications.`

The content is perfectly readable. Only the configuration fails.

**The same static UI string, read two different ways in two frames:**

```
'* Mis tip: Use /clear to start 7kesh when switching topics and free up context'
'* Mistip: Use /clear to start fresh when switching topics and free up context'
```

`fresh` → `7kesh`. Searching `recall` for "fresh" misses that frame entirely. Also
`'- Tip: …'` vs `'L Tip: …'`, and `'position depends or'` vs `'position depends on'`.

---

## 3. The measured relationship between input size and accuracy

Synthetic fixture: a dense page of real macOS UI text at real point sizes (13 pt labels, 11 pt
secondary-grey helper text, 11–12 pt monospace identifiers), rendered at 2x, then downscaled to each
input size with the same `CGContext` + `.high` interpolation the app itself uses. Vision
`.accurate`, `en-US`, revision 3. `prose` and `ident` are needle recall **by occurrence count** — the
block repeats down the page, so "found 2 of the 4 times it appears" is a partial failure a boolean
`contains` would hide.

**Built-in geometry (1512 × 949 pt, 45 lines, native 3024 px):**

| OCR input width | CER | prose recall | identifier recall | ms |
|---|---|---|---|---|
| **1512 — today** | 0.5% | 94% | **88%** | 784 |
| 1600 | 0.6% | 100% | 98% | 772 |
| 2000 | 0.5% | 100% | 86% | 793 |
| 2400 | **0.3%** | 100% | 96% | 781 |
| 3024 — native 2x | 4.2% | 88% | 75% | 924 |

Repeated with grayscale antialiasing instead of LCD smoothing, to rule the renderer out:

| OCR input width | CER | prose | identifier | ms |
|---|---|---|---|---|
| **1512 — today** | 4.3% | 76% | **69%** | 668 |
| 1600 | 1.3% | 100% | 94% | 789 |
| 2000 | 0.4% | 100% | 90% | 908 |
| 2400 | 1.6% | 100% | 96% | 874 |
| 3024 — native 2x | 6.8% | 82% | 67% | 795 |

**External 4K geometry (1920 × 1080 pt, 51 lines, native 3840 px):**

| OCR input width | CER | prose | identifier | ms |
|---|---|---|---|---|
| **1600 — today** | **19.6%** | 68% | **32%** | 925 |
| 1920 — 1x, unclamped | 7.2% | 50% | 51% | 759 |
| 2000 | 12.5% | 50% | 51% | 955 |
| 2400 | **6.6%** | 68% | 58% | 759 |
| 3024 | 10.5% | 45% | 43% | 793 |
| 3840 — native 2x | 5.2% | 59% | 45% | 769 |

Three things follow, and only the first is obvious:

1. **Today's configuration is the worst or near-worst tested**, and catastrophically so on the wide
   display: 32% identifier recall means two thirds of the searchable terms on screen were destroyed.
2. **Accuracy is non-monotonic in input size, with an optimum.** 2400 px is best or tied-best in all
   three runs; 3024 px and above is consistently *worse than today*. Vision's `.accurate` recogniser
   has a preferred input-size band for a screenful of UI text, and both sides of it are bad.
3. **Latency is flat across the whole range** (0.67–0.96 s in this fixture). Vision's cost tracks the
   number of text regions, not pixel count, so input size is an accuracy decision, not a cost one.

---

## 4. What to change

### 4.1 Decouple the OCR input size from the JPEG size, and derive it from pixels — required

Replace the tunable and `captureSize`:

```swift
/// Longest side of the stored JPEG. Storage only — it must never decide what Vision sees.
static let maxPixelSize = 1600

/// Longest side of the image handed to Vision. Measured, not chosen: `.accurate` recognition of a
/// screenful of UI text is non-monotonic in input size and peaks near 2400 px on the longest side —
/// 1512 and 3024 are both materially worse. Re-run the sweep in docs/ocr-quality.md before moving it.
static let ocrMaxPixelSize = 2400

/// Pixel dimensions to capture. `contentRect` is in *points* while `SCStreamConfiguration.width` is
/// in *pixels*, so passing the point size through captures a Retina window at 1x and halves every
/// glyph before Vision sees it. Scaled up towards the backing store, capped at `ocrMaxPixelSize`,
/// and never taken below 1x: shrinking under the point size throws away text that was on the screen.
/// A zero-area window makes the ratio NaN, and `Int(NaN)` traps rather than throwing — so a
/// degenerate frame is refused here instead of crashing the app.
static func captureSize(for rect: CGRect, pointPixelScale: CGFloat) -> (width: Int, height: Int)? {
    guard rect.width > 0, rect.height > 0, rect.width.isFinite, rect.height.isFinite
    else { return nil }

    let backing = (pointPixelScale.isFinite && pointPixelScale >= 1) ? pointPixelScale : 1
    let longestPoints = max(rect.width, rect.height)
    let target = min(longestPoints * backing, CGFloat(ocrMaxPixelSize))
    let factor = max(1, target / longestPoints)
    return (
        max(1, Int((rect.width * factor).rounded())),
        max(1, Int((rect.height * factor).rounded()))
    )
}
```

and the call site (`ScreenWatcher.capture`, currently line 253):

```swift
private func capture(_ window: SCWindow) async -> CGImage? {
    // The filter is the authority on what will actually be captured and at what backing scale;
    // `window.frame` knows neither. Both properties are macOS 14.0+, and the floor here is 14.4.
    let filter = SCContentFilter(desktopIndependentWindow: window)
    guard let size = ScreenPipeline.captureSize(
        for: filter.contentRect,
        pointPixelScale: CGFloat(filter.pointPixelScale)
    ) else {
        noteSkip("window has no area")
        return nil
    }

    let config = SCStreamConfiguration()
    config.width = size.width
    config.height = size.height
    config.scalesToFit = true
    config.showsCursor = false
    // Prefer the native backing store over a nominal-resolution source.
    config.captureResolution = .best

    do {
        return try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
    } catch {
        noteError("Capture failed: \(error.localizedDescription)")
        return nil
    }
}
```

Effect on this machine: built-in full-screen window 1512 → 2400 px; external 4K 1600 → 2400 px (and
it stops being a sub-1x downscale); a 723 pt window 723 → 1446 px.

**Storage cost: zero.** `writeJPEG` already calls `downscaled(image, longestSide: maxPixelSize)`;
today that is a no-op and after this change it does real work, holding the stored JPEG at ≤ 1600
exactly as now. Memory rises from ~5.7 MB to ~14 MB per in-flight BGRA capture, inside the existing
`autoreleasepool` in `ScreenPipeline.process`.

**Tradeoff:** 2400 is an empirical optimum from one fixture family on one machine. It is a large
improvement over both endpoints in every run measured, but it is a *measured setting*, not a derived
one — which is exactly why it must land with the harness in §5 rather than on its own.

### 4.2 Pin the Vision revision — required, and required *before* measuring

```swift
request.revision = VNRecognizeTextRequestRevision3
```

Revisions 1 and 2 are deprecated as of macOS 15; 3 is current and available from macOS 13, and is the
newest constant the macOS 26 SDK defines — so this is a behavioural no-op today. Without it the
request uses whatever `currentRevision` the running OS ships, so a macOS update silently changes the
OCR corpus and invalidates every before/after number. No tradeoff; the cost is having to revisit it
deliberately when a revision 4 appears, which is the point.

### 4.3 Re-check the dedup calibration — required follow-up

`dedupeDistance = 5` was tuned empirically ("a spinner differs by 1 bit, a moved text cursor by ~4, a
real content change by 20+") at today's capture size. `dHash` runs on the captured image, so a 9 × 8
downsample now averages ~2.5x more source pixels per cell. Log hamming distances for an hour after
the change and confirm the two populations still separate at 5; if they do not, an idle screen starts
costing a full OCR pass every tick, or real changes start being dropped.

### 4.4 Leave `usesLanguageCorrection = true`, and do not add `customWords` — do nothing

See §6. Measured: no accuracy effect in either direction, in any arm. It is a latency lever only
(464 ms vs 801 ms, and 491 ms vs 769 ms, on identical images). If the OCR pass ever becomes a battery
problem, turning it off is worth ~1.7x — but re-measure against the harness rather than assuming it
is free, because it was very slightly *better* on prose in both native arms.

### 4.5 Leave `minimumTextHeight` unset — do nothing

Ruled out from the SDK header, which documents the default as `0.0` and states: *"If the minimum
height is set to 0.0 the image gets processed at the highest possible resolution with no downscaling.
With that the processing time will be the longest and the memory usage the highest but the smallest
technically readable text will be recognized."* The code never sets it, so Vision is **already**
running at the maximum resolution of the image it is given. There is no accuracy left on this lever;
the only thing limiting glyph height is the image the app hands it, which is §4.1.

### 4.6 Leave `recognitionLevel = .accurate` — do nothing, but put it on the record

Not re-measured here. Add a `.fast` arm to the sweep so the choice is evidence rather than an
inherited default.

---

## 5. How to measure this

Nothing above should be trusted on a second machine without re-running it, and the non-monotonicity
in §3 means the right value **cannot be guessed**. The harness is part of the fix, not an extra.

### 5.1 The blocker: none of this is reachable from a test today

- `ScreenPipeline` is `private` at file scope, so `recognizeText` and `captureSize` cannot be called
  from anywhere but `ScreenWatcher.swift`.
- `ContextApp` is an `executableTarget`, and `Package.swift` declares only `ContextCoreTests` and
  `ContextMCPKitTests` — so even non-private code there cannot be imported by a test target.

That is why a resolution regression could ship unnoticed. The destination is to extract the pure
image/OCR half into a `ContextCapture` library target (Vision + CoreGraphics only — the OCR half
needs no ScreenCaptureKit) that `ContextApp` depends on, plus a `ContextCaptureTests` target: the
same move `ContextMCPKit` already makes, "kept out of the executable so it is testable". **That edits
`Package.swift`, which `CONTRACTS.md` reserves — it is a request to the integrator, not something to
do unilaterally.** The immediate step that needs no such change is `scripts/ocr-eval.swift`, a
standalone `swift` script driving the identical Vision configuration over a fixture directory.

### 5.2 Fixture corpus

`Tests/Fixtures/OCR/<name>.png` + `<name>.truth.txt` + `<name>.needles.tsv` (`prose|ident<TAB>string`).

- **PNGs are checked in at native Retina resolution.** A fixture regenerated at test time measures
  the renderer as well as the recogniser, and drifts under you when AppKit changes.
- Two kinds. **Generated pages**, whose ground truth *is* the source string, so it cannot be
  mis-transcribed — cheap to make and impossible to get wrong. **Real screenshots**, transcribed by
  hand once: the System Settings Screen Recording pane, an iTerm window, a Cursor buffer, and a
  browser address bar showing a real UUID URL, because those are the four failures in evidence.
- Needles are the strings a user would actually search for, split into `prose` and `ident` buckets.
  The whole question is prose-versus-identifier, and one aggregate number hides it.

### 5.3 Metrics — and why CER alone is not enough

Per fixture, per configuration:

- **CER** — Levenshtein(normalised OCR, normalised truth) / len(normalised truth), whitespace
  collapsed. Report case-sensitive **and** case-folded, so `ITerm` vs `iTerm` shows up as its own
  number rather than vanishing.
- **Needle recall by occurrence**, prose and identifier reported separately:
  `min(occurrences in OCR, occurrences in truth) / occurrences in truth`.
- **Latency** in ms, and input pixel count.
- **Stability** — run each configuration 3× and at ±5% input scale, and count distinct outputs.

CER alone would have passed the configuration that is shipping: in the built-in fixture at today's
1512 px, **CER was 0.5% while identifier recall was 88%**; on the external at today's 1600 px, **CER
was 19.6% while prose recall was still 68%**. Identifiers are a tiny share of the characters and the
entire share of the product failures, because `recall` is a token search — the metric that predicts
user-visible failure is whether the exact token survived.

### 5.4 Field metric — no fixtures, no ground truth, real usage

The same static UI string is captured hundreds of times a day. Every disagreement between two
captures of it is an error, provable without knowing what it said:

1. Group every OCR line by an aggressive normal form (lowercase, strip non-alphanumerics); any group
   with more than one raw variant disagreed with itself on case or punctuation.
2. Pair lines within edit distance ≤ 3 to catch substantive disagreements (`fresh` / `7kesh`).

Baseline measured on the current database — 942 frames, 49,704 OCR lines, 15,301 distinct, from one
day of real use:

| measure | value |
|---|---|
| repeated-content groups | 5,405 |
| …rendered inconsistently | **1,356 (25%)** |
| near-duplicate line pairs (edit distance ≤ 3) | **4,575** |

Both numbers should fall after §4.1. This over-counts genuinely-changing content (timers, token
counters, clocks), so it is a trend measure between comparable days, not an absolute — but it needs
no fixtures and it runs on exactly the data the product ships.

### 5.5 The decision rule

Because the relationship is non-monotonic, sweep rather than pick: `{1x point size, 1600, 2000, 2400,
3024, native}` × `{correction on, off}` × `{.accurate, .fast}` over the corpus, print the table, and
choose the input size with the highest **identifier** recall, tied on CER, then on latency. Re-run
when the pinned Vision revision changes.

### 5.6 The gate to check in

Once the sweep has chosen a size, freeze it: identifier occurrence recall ≥ 0.95 and CER ≤ 2% on the
**generated** fixtures at the chosen configuration. Report the real-screenshot fixtures without
gating them — they are noisier, and a flaky gate is worse than none.

---

## 6. What is *not* the cause

Stated as likely culprits, and ruled out by measurement rather than argument:

**`usesLanguageCorrection = true` "correcting" identifiers.** Not reproduced, in any arm.
`iTerm`/`iTerm2` came back **exactly right with correction both on and off**, at every input size in
band; identifier recall was within noise between on and off in all four comparisons; and
`customWords` (`iTerm`, `kubectl`, `nginx`, `pointPixelScale`, …) changed nothing at all. Note also
that `customWords` supplements the lexicon at the word-recognition stage, so it and
`usesLanguageCorrection = false` are mutually exclusive in practice — a fork that turns out not to
matter. The reported failures are the wrong *shape* for a lexicon artifact: language correction
snaps a token toward a dictionary word, whereas `0`→`Q` and `i`→`I` are glyph confusions, and one
URL read two different ways is not a correction at all — a lexicon is deterministic.

**Native-resolution capture as the fix.** This is the important one: **it is not, and taken
literally it makes things worse.** OCR at full native pixels scored *below today's configuration* in
both built-in runs (CER 4.2% / 6.8% and identifier recall 75% / 67%, versus 88% / 69% today), and it
was the second-worst arm on the external display. Re-tested with grayscale antialiasing to rule out
a subpixel-rendering artifact in the fixture, and the shape held. Capturing at native pixels and
then *capping the OCR input at ~2400 px* is the change that helps; "OCR the native image" is not.

**`minimumTextHeight`.** Already at its most permissive default (§4.5). Nothing to change.

**JPEG quality 0.5.** Irrelevant. `ScreenPipeline.process` runs `recognizeText` on the in-memory
`CGImage` and encodes the JPEG afterwards; the recogniser never sees a compressed pixel.

---

## 7. Out of scope, noticed while measuring

The live database contains OCR of the System Settings **Screen & System Audio Recording** pane,
including the full list of apps granted screen recording. `isSensitiveSettingsWindow` matches on
window titles containing `privacy`/`security`/`password`/…, and that pane's title is
`Screen & System Audio Recording`, which matches none of them. This belongs to the redaction work
being done in the same file — flagged here only because the evidence surfaced it.

---

## 8. Reproducing all of it

```bash
# Display geometry: points, backing scale, native pixels.
swift - <<'EOF'
import AppKit
for s in NSScreen.screens {
    print("points=\(Int(s.frame.width))x\(Int(s.frame.height)) scale=\(s.backingScaleFactor)")
}
EOF

# What the app actually fed Vision: stored JPEG width == OCR input width (see §1.3).
DB="$HOME/Library/Application Support/ContextForClaude/context.db"
sqlite3 "$DB" "select imagePath from frames where imagePath is not null;" | shuf -n 120 |
  while read -r p; do sips -g pixelWidth "$p" 2>/dev/null | awk '/pixelWidth/{print $2}'; done |
  sort -n | uniq -c

# The mis-read that is in the database, and the display it came from.
sqlite3 "$DB" "select imagePath from frames where ocrText like '%ITerm%';" |
  while read -r p; do sips -g pixelWidth -g pixelHeight "$p"; done
```

The input-size sweep and the self-consistency scan are the two programs to check in as
`scripts/ocr-eval.swift` and `scripts/ocr-consistency.py`; their measured output is in §3 and §5.4.
Both were run for this document as standalone scripts — no `swift build`, no package changes — which
is also how they should run until `ContextCapture` exists.
