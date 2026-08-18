import AppKit
import CoreGraphics
import ScreenCaptureKit
import Vision

//  Finding our row when the accessibility tree is shut — by **looking at the pane** instead.
//
//  `PermissionChoreography`'s header records the measurement that closes every accessibility route
//  during the Accessibility grant: from a process with `AXIsProcessTrusted() == false`, every read of
//  System Settings' tree answers `kAXErrorAPIDisabled`, down to the attribute *name* list, down to
//  hit-testing by position, and down to asking System Events to do the read on our behalf. The gate
//  is on the sender. So the row that grants Accessibility cannot be located by asking — the one step
//  that most needs the answer is the one step forbidden from having it.
//
//  That header then concluded there was nothing left to do, and the conclusion was wrong. It is only
//  true of the *accessibility* API. **This app is a screen recorder with OCR**, and Screen Recording
//  is a different grant with a different gate: with it, we may read the pixels of another
//  application's window with no Accessibility check anywhere in the path. The row is right there on
//  screen with its name written on it in 13 pt text, and the app already owns both halves of reading
//  it — `ScreenPipeline.capture` takes the picture, `ScreenPipeline.recognizeText` reads it.
//
//  So this is the second locator: same job as `SettingsRowLocator`, same output
//  (`SettingsSpotlightTarget`), no Accessibility anywhere. It is not a replacement — the accessibility
//  walk is better wherever it works, because it reads the switch's own frame and its own state rather
//  than deriving them. This is what runs when that walk cannot answer.
//
//  **What it costs.** Measured live on macOS 26.5.2 (25F84) against Privacy & Security ▸
//  Accessibility, System Settings 723 × 948 on a 2× display, four consecutive passes:
//
//  | stage                                | cold   | warm            |
//  |--------------------------------------|--------|-----------------|
//  | `CGWindowListCopyWindowInfo`         |  43 ms |  1.5 – 3.6 ms   |
//  | `SCShareableContent`                 |  21 ms | 14 – 15 ms      |
//  | `SCScreenshotManager.captureImage`   | 128 ms | 58 – 63 ms      |
//  | `VNRecognizeTextRequest` (.accurate) | 550 ms | 328 – 357 ms    |
//  | **total**                            | 743 ms | **407 – 434 ms**|
//
//  That is the same order as the accessibility walk this stands in for (270–727 ms, measured in
//  `SpotlightTrackPolicy`), which is the whole argument for the schedule below: **one schedule per
//  cost, not one per tier.** A pass is expensive, so it runs on `SpotlightTrackPolicy.fullSolve`'s
//  cadence and never on the 40 ms tick — and it runs *off* the solver, so the solver never waits for
//  one. See `SettingsPaneSightings`.
//
//  **What it refuses to claim.** The rule this whole surface is arranged around does not change: a
//  confident arrow aimed at nothing is worse than a sentence. OCR adds two new ways to be wrong and
//  both are refused rather than smoothed over — a name read out of the wrong pixels (guarded by an
//  exact, whole-string match and a confidence floor) and a name read out of a pane we are not
//  actually looking at (guarded by the reading carrying the window and the capability it was taken
//  for). A row that is scrolled out of the list cannot be sighted at all, which is a property of
//  pixels rather than a check: text that is not drawn is not there to read.

// MARK: - What Vision answered

/// One recognised run of text and where it sat.
///
/// The seam that makes the whole locator testable with no System Settings, no screen recorder and no
/// grant: `SettingsRowSighting` is a pure function of an array of these, exactly as
/// `SettingsRowLocator` is a pure function of a `SettingsElement` tree.
struct RecognizedLabel: Equatable, Sendable {
    var text: String
    /// Vision's own normalised rect: origin **bottom-left**, 0–1 on both axes, measured against the
    /// image handed to it. Kept in Vision's terms rather than converted at the seam so a test can
    /// paste an observation's `boundingBox` in verbatim — the numbers in `SettingsRowSightingTests`
    /// are the ones a live pass printed.
    var boundingBox: CGRect
    /// `VNRecognizedText.confidence`, 0–1. Live on the Accessibility pane this reads **1.0** for our
    /// row at `.accurate`; the floor exists for the blurred, half-composited frame captured during a
    /// pane transition, not for the steady state.
    var confidence: Float
}

// MARK: - The sighting

/// Locates one application's row in a Privacy & Security pane from the **pixels** of that pane.
///
/// Pure, and deliberately so: the conversion from a normalised Vision box to a rect on somebody's
/// second monitor is exactly the kind of arithmetic that is right on the machine it was written on
/// and silently wrong everywhere else — the same reason `ScreenSpace` is a value over an explicit
/// list of displays rather than a method that reads `NSScreen`.
struct SettingsRowSighting {
    /// The name System Settings lists us under. `PermissionChoreography.appDisplayName`, which is
    /// `CFBundleName` — the same string the accessibility walk matches on, so a rename cannot move
    /// the two locators apart.
    let appName: String
    var limits = Limits()

    struct Limits {
        /// How sure Vision has to be before a match is allowed to aim an arrow.
        ///
        /// Measured on the live pane: `.accurate` answers **1.0** for our row, so this is not a
        /// threshold the steady state is anywhere near. It is here for the frames that are not the
        /// steady state — a capture taken mid pane-transition, or while System Settings is
        /// re-compositing — where a half-drawn string can still be read as something.
        var minimumConfidence: Float = 0.6
    }

    /// Where the pixels say the row is — or why they do not.
    ///
    /// Three failures rather than one, because they are three different facts and only one of them
    /// is worth re-taking quickly. All three refuse to point.
    enum Outcome: Equatable {
        case sighted(SettingsSpotlightTarget)
        /// The name was read, and not confidently enough to aim at.
        case faint
        /// The pane was read and our name is not in it — which on this tier also covers "the row is
        /// scrolled out of the list", because text that is not drawn cannot be recognised.
        case notFound
    }

    // MARK: The pane's shape, measured

    //  The three numbers below are the whole of what this locator infers, and each is a *horizontal*
    //  fact about a Privacy list. That split is the point and it is what keeps the claim honest:
    //  **which row this is, is measured — its y comes from the glyphs of our own name. How far the
    //  row runs, is inferred.** A generous horizontal band can only ever ring more of the right row;
    //  it cannot ring the wrong one.
    //
    //  Measured twice, independently, on macOS 26.5.2 (build 25F84), and the two agree exactly:
    //
    //  1. **From the pixels.** Privacy & Security ▸ Accessibility, window at (576, 65) 723 × 948 on a
    //     2× display. Row separators either side of our row at image y 657 and 737 → a **40 pt** row.
    //     The switch's blue pill occupies image x 1314…1385, y 686…717 → **36 × 16 pt** at global
    //     x 1233…1269, and the window's right edge is 1299, so the switch's right edge sits **30 pt**
    //     in from it. The list card runs global x 819…1279 — 460 pt wide, 20 pt in from the window's
    //     right edge.
    //  2. **From the accessibility tree.** `PaneFixture`, dumped off the real Screen Recording and
    //     Accessibility panes by an earlier measurement with the window at (360, 34) 723 × 948:
    //     toggle `x: 1017, width: 36, height: 16` against a window whose right edge is 1083 — the
    //     same 36 × 16 switch, the same 30 pt inset — inside a section `x: 603, width: 460`, the same
    //     460 pt card 20 pt in from the same edge.
    //
    //  Two measurements, two window positions, two panes, one answer. That is why these are constants
    //  and not a guess, and it is also why they are stated as insets **from the window's right edge**
    //  — the one edge the window server is authoritative about — rather than as absolute positions.

    /// The switch, as System Settings draws it.
    static let toggleSize = CGSize(width: 36, height: 16)
    /// How far the switch's right edge sits in from the window's right edge.
    static let toggleTrailingInset: CGFloat = 30
    /// One row of a Privacy list, separator to separator.
    static let rowHeight: CGFloat = 40

    // MARK: The lookup

    /// Reads `labels` for our row.
    ///
    /// `window` is System Settings' frame in global CoreGraphics points **as the capture was taken
    /// against it** — `SCContentFilter.contentRect`, which measured identical to both `SCWindow.frame`
    /// and `CGWindowListCopyWindowInfo`'s bounds on macOS 26.5.2. It is the whole coordinate system:
    /// Vision measures 0–1 against the image, the image *is* this rect, so the conversion is one
    /// multiply and one flip and depends on nothing else.
    ///
    /// `occurrence` is the same ordinal `SettingsRowLocator.locate(in:preferring:)` takes and comes
    /// from the same `PermissionChoreography.sectionOccurrence(for:)`, because the pane it disambiguates
    /// is the same pane: Screen & System Audio Recording lists an application **twice**, and system
    /// audio's switch is in the second list. Sections are laid out top to bottom, so sorting the
    /// matches by their y reproduces the section order the tree walk gets structurally — confirmed
    /// live, where that pane yielded exactly two matches for our name at global y 435.5 and 1011.5,
    /// upper list then lower. Unlike the walk this does **not** clamp the ordinal: a section is a
    /// structural fact and a match is not, so asking for the second of one match is a question with
    /// no answer rather than a reason to point at the first.
    func locate(in labels: [RecognizedLabel], window: CGRect, preferring occurrence: Int = 0) -> Outcome {
        guard window.width > 0, window.height > 0, occurrence >= 0 else { return .notFound }

        let wanted = Self.normalised(appName)
        var faint = false
        var matches: [CGRect] = []
        for label in labels where Self.normalised(label.text) == wanted {
            // Confidence is checked before geometry so a faint match is reported as faint rather
            // than disappearing into `notFound` — the two deserve different re-take schedules and,
            // one day, different sentences.
            guard label.confidence >= limits.minimumConfidence else {
                faint = true
                continue
            }
            guard let rect = Self.pointRect(of: label.boundingBox, in: window) else { continue }
            matches.append(rect)
        }

        guard !matches.isEmpty else { return faint ? .faint : .notFound }
        matches.sort { $0.minY < $1.minY }
        guard occurrence < matches.count else { return .notFound }

        guard let target = Self.target(labelled: matches[occurrence], in: window) else { return .notFound }
        return .sighted(target)
    }

    /// Vision's normalised, bottom-left-origin box → global CoreGraphics points, top-left origin.
    ///
    /// The flip is `1 - y - height` and **not** `1 - y`, for the reason `LiveTextBlock.screenRect`
    /// spells out: the latter maps the box's bottom edge onto the new top edge, so every rect lands
    /// one box-height too high — a rounding error on a line of small text and nonsense on a heading.
    /// Here it would be a row's worth of error on a 40 pt row, which is the wrong row.
    static func pointRect(of box: CGRect, in window: CGRect) -> CGRect? {
        guard box.origin.x.isFinite, box.origin.y.isFinite, box.width.isFinite, box.height.isFinite,
            box.width > 0, box.height > 0
        else { return nil }
        let rect = CGRect(
            x: window.minX + box.minX * window.width,
            y: window.minY + (1 - box.maxY) * window.height,
            width: box.width * window.width,
            height: box.height * window.height)
        // A box Vision measured outside the image it was handed is not a box; refusing is cheaper
        // than reasoning about what it might have meant.
        return window.insetBy(dx: -1, dy: -1).contains(rect) ? rect : nil
    }

    /// The row, the switch and the target, built out of one measured label and one measured window.
    ///
    /// The row runs from the label's own left edge to the switch's right edge, which is **the same
    /// band `SettingsRowLocator` reports** — its `row(in:children:clips:section:)` answers
    /// `label.union(toggle)`, not the list row's full width. The two locators therefore dash the same
    /// rectangle, and the user cannot tell which one found it. That is the intended result.
    static func target(labelled label: CGRect, in window: CGRect) -> SettingsSpotlightTarget? {
        let toggle = CGRect(
            x: window.maxX - toggleTrailingInset - toggleSize.width,
            y: label.midY - toggleSize.height / 2,
            width: toggleSize.width,
            height: toggleSize.height)
        // A window too narrow to hold a label and a switch side by side is not a pane we measured,
        // and a band of negative width would be drawn as a rectangle somewhere it does not belong.
        guard toggle.minX > label.maxX else { return nil }

        // Vertically centred on the glyphs and floored to a whole row. The glyph box is 12.5 pt tall
        // against a 40 pt row and sits 2.2 pt below the row's centre — cap height has no descender —
        // so this lands within about two points of the separators either side. The dashes are laid
        // 5 pt outside whatever they surround, so that is inside the line's own width.
        let band = CGRect(x: label.minX, y: label.midY - rowHeight / 2, width: toggle.maxX - label.minX, height: rowHeight)
            .intersection(window)
        guard !band.isNull, band.width > 0, band.height > 0 else { return nil }

        return SettingsSpotlightTarget(
            row: band,
            toggle: toggle,
            // **Not a claim about the pixels.** Nothing in a screenshot says whether a switch is on,
            // and nothing here tries: this tier is only ever reached while an episode is standing in
            // System Settings *waiting for a grant that has not landed*, so "off" is the state the
            // caller already established from TCC. When it lands, the episode ends and the overlay
            // is taken down by `confirmGranted` rather than re-solved.
            isOn: false,
            // The same floor the accessibility walk applies, for the same reason: a 36 × 16 sliver
            // glowed exactly reads as a smudge on the row. Centred on the switch, never moved off it.
            focus: toggle.atLeast(width: 56, height: 30),
            // **The window, and not an invented list.** This tier cannot see the pane's structure —
            // there is no caption, no scroll area and no **+** button to measure, only text — so the
            // one rect it may honestly hand the scrim is the one the window server gave it. That is
            // exactly what the `framing` tier already opens its hole in; the difference is that this
            // one also knows which row inside it to dash.
            area: window,
            list: nil,
            isListed: true,
            gesture: .click,
            window: window)
    }

    /// Case- and whitespace-insensitive, and **whole-string**.
    ///
    /// Whole-string is the load-bearing half. A `contains` test would match "Context for Claude
    /// Helper", and — measured live on the very pane this exists for — it would also have to be told
    /// apart from the rows for "Claude", "Coast Local" and "Codex Computer Use", all of which were in
    /// the list a few rows above ours and two of which contain the word this app is named after.
    private static func normalised(_ text: String) -> String {
        text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }
}

// MARK: - Reading the pane

/// One capture-and-recognise pass over System Settings' window.
///
/// Split from both the cache above it and the geometry beside it because this is the only part that
/// cannot be tested — it needs a live window server, a live System Settings and a real grant. Keeping
/// it to "hand back what Vision saw" is what leaves every decision on the testable side of the seam.
enum SettingsPaneReader {

    /// Reads the text out of one window, or answers `nil` when it cannot be read at all.
    ///
    /// Answers the window rect the capture was actually taken against as well as the text, because
    /// the two are one fact: the normalised boxes mean nothing without the rect they were measured
    /// in, and re-reading the window's frame afterwards would be reading it at a different instant
    /// than the pixels were taken at — which on a window being dragged is a whole overlay's worth of
    /// error.
    static func read(bundleID: String = SettingsWindowProbe.systemSettingsBundleID) async
        -> (window: CGRect, labels: [RecognizedLabel])?
    {
        // Cheap negative filter. `CGPreflightScreenCaptureAccess` says whether the *grant* exists; it
        // cannot say whether this process's window-server connection carries it, because the window
        // server fixes that when the process connects and a grant made since applies to the next
        // process rather than this one. So a `true` here is not permission to trust the capture — the
        // capture still has to succeed — but a `false` is a definite no, and skipping the whole pass
        // on it keeps an ungranted first run from throwing an SCK error every 800 ms.
        guard CGPreflightScreenCaptureAccess() else { return nil }
        guard let window = SettingsWindowProbe.window(bundleID: bundleID) else { return nil }

        do {
            let content = try await SCShareableContent.excludingDesktopWindows(
                false, onScreenWindowsOnly: true)
            guard let target = content.windows.first(where: { $0.windowID == window.id }) else {
                return nil
            }
            let filter = SCContentFilter(desktopIndependentWindow: target)
            // The filter, and not the window's frame, is the authority on what will be captured and
            // at what backing scale — the same reason `ScreenWatcher.capture(_:)` reads it. Measured
            // on macOS 26.5.2: `contentRect` answered identically to `SCWindow.frame` and to
            // `CGWindowListCopyWindowInfo`'s bounds, at (576, 65, 723, 948) and again at
            // (-64, 109, 723, 948) after the window was dragged.
            let rect = filter.contentRect
            guard let size = captureSize(for: rect, pointPixelScale: CGFloat(filter.pointPixelScale))
            else { return nil }

            let config = SCStreamConfiguration()
            config.width = size.width
            config.height = size.height
            config.scalesToFit = true
            config.showsCursor = false
            config.captureResolution = .best
            // The shadow is not part of the window and would shift every normalised box by its width.
            config.ignoreShadowsSingleWindow = true

            let image = try await SCScreenshotManager.captureImage(
                contentFilter: filter, configuration: config)
            return (rect, recognise(in: image))
        } catch {
            // Ordinary rather than exceptional: this is what an ungranted process, or one that was
            // granted since it connected to the window server, gets. The caller degrades to the
            // written instruction, which is what it was already showing.
            ContextLog.info(
                "sighting: could not capture the System Settings window (\(error.localizedDescription))",
                "permissions")
            return nil
        }
    }

    /// Pixel dimensions to ask for: the window at its own backing store, and nothing else.
    ///
    /// `SCContentFilter.contentRect` is in **points** while `SCStreamConfiguration.width`/`.height`
    /// are in pixels, and passing the point size straight through is the mistake
    /// `ScreenPipeline.captureSize` documents at length — a Retina window captured at 1× halves every
    /// glyph before Vision sees it. That function is file-private to the capture pipeline and is not
    /// the same problem anyway: it exists to raise an *arbitrary* window towards its backing store and
    /// cap it at `ocrMaxPixelSize` so an ultrawide does not cost a second of Vision. This has one
    /// known subject — a System Settings pane, 723 × 948 on every machine measured — whose native 2×
    /// capture is 1446 × 1896, comfortably under any such cap, and which is exactly the size every
    /// timing in this file's header was taken at.
    ///
    /// The zero-area guard is not decoration: `Int(NaN)` traps rather than throwing, so a degenerate
    /// rect has to be refused here or it crashes the app.
    private static func captureSize(for rect: CGRect, pointPixelScale: CGFloat) -> (width: Int, height: Int)? {
        guard rect.width > 0, rect.height > 0, rect.width.isFinite, rect.height.isFinite
        else { return nil }
        let scale = (pointPixelScale.isFinite && pointPixelScale >= 1) ? pointPixelScale : 1
        return (
            max(1, Int((rect.width * scale).rounded())),
            max(1, Int((rect.height * scale).rounded()))
        )
    }

    /// Vision over one captured window.
    ///
    /// Configured **identically** to `ScreenPipeline.recognizeText` — `.accurate`, `en-US`,
    /// `VNRecognizeTextRequestRevision3`, `minimumTextHeight = 0` — which `Rewind/LiveText` also
    /// mirrors, for the same reason each time: one recogniser configuration in the app, so what one
    /// surface can read another can too. It was worth re-measuring rather than assuming here, and the
    /// measurement is why the pinned configuration also happens to be the right one:
    ///
    /// - `.fast` reads the pane in 73 ms instead of 330 ms and is **not** usable. It reports a
    ///   constant `confidence` of 0.5 for every string, so the floor above becomes meaningless, and
    ///   at 1× it missed our row entirely (0 of 3 matches) where `.accurate` found it.
    /// - Raising `minimumTextHeight` buys nothing: 0.008 measured within noise of 0, and 0.02 dropped
    ///   `.fast` to zero observations.
    ///
    /// Unlike capture, the result is **not** scrubbed through `Redaction`, for the same reason
    /// `LiveTextRecognizer` is not: nothing here is stored, indexed or handed to a model. The strings
    /// live for one comparison against this app's own name and are dropped.
    private static func recognise(in image: CGImage) -> [RecognizedLabel] {
        let sink = LabelSink()
        let request = VNRecognizeTextRequest { request, error in
            if error != nil { return }
            guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
            // Defensive copy for the same reason capture and Live Text both make one: Vision hands
            // back a bridged NSArray whose buffer can be released underneath an enumeration, which
            // traps the process rather than throwing (omi #5891, #5151).
            sink.observations = Array(observations)
        }
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        request.recognitionLanguages = ["en-US"]
        request.revision = VNRecognizeTextRequestRevision3
        request.minimumTextHeight = 0

        do {
            try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
        } catch {
            return []
        }

        return sink.observations.compactMap { observation in
            guard let candidate = observation.topCandidates(1).first, !candidate.string.isEmpty
            else { return nil }
            return RecognizedLabel(
                text: candidate.string,
                boundingBox: observation.boundingBox,
                confidence: candidate.confidence)
        }
    }

    /// Vision writes its observations synchronously inside `perform`, before it returns, so this box
    /// is never touched from two threads despite the block signature permitting it.
    private final class LabelSink: @unchecked Sendable {
        var observations: [VNRecognizedTextObservation] = []
    }
}

// MARK: - Paying for it once

/// The most recent reading of System Settings' pixels, and the schedule that keeps taking one from
/// costing anything the user can feel.
///
/// **Nothing here ever blocks the solver.** That is the single design constraint. `liveGuidance` is
/// synchronous and runs on the overlay's tick; a pass costs 407–434 ms warm, and a tick that waited
/// for one would be the 727 ms main-actor stall this whole surface was rewritten to remove, wearing a
/// different hat. So a caller asking for the pane's text gets **whatever was last read**, and a fresh
/// pass is started behind them if what they got is stale. The first tick of an episode therefore
/// answers with nothing and the overlay shows the written instruction — which is what it was showing
/// anyway — and the tick after the pass lands upgrades it to an arrow. `SpotlightHysteresis` believes
/// a *better* answer immediately, so nothing has to wait for that.
///
/// A reading is kept only for the exact window **and** the exact capability it was taken for. The
/// window because the normalised boxes are meaningless against any other rect. The capability because
/// System Settings keeps the same window when it changes pane, so the window alone cannot tell
/// "Accessibility, still" from "Screen Recording, now" — and both panes list this application.
final class SettingsPaneSightings: @unchecked Sendable {
    static let shared = SettingsPaneSightings()

    /// How old a reading may be before another is worth taking.
    ///
    /// `SpotlightTrackPolicy.fullSolve`, deliberately the same number and for the same reason it is
    /// that number there: what makes a re-solve expensive is the walk, a pass here costs the same
    /// order as the walk (407–434 ms against 270–727 ms), and only the tiers that perform one have to
    /// be rationed. One schedule per cost, not one per tier.
    static var refreshInterval: Duration { SpotlightTrackPolicy().fullSolve }

    private struct Reading {
        var capability: Capability
        var window: CGRect
        var labels: [RecognizedLabel]
        var takenAt: ContinuousClock.Instant
    }

    private let lock = NSLock()
    private var reading: Reading?
    private var refreshing = false
    /// When a pass was last *started*, whether or not it produced anything. What the schedule is on.
    private var lastAttempt: ContinuousClock.Instant?
    /// Whether this episode has already recorded the provider switch. Once, not once a tick.
    private var announced = false
    private var passes = 0
    /// Bumped by `forget()`. A pass carries the generation it was started in and drops its result if
    /// that has moved on — otherwise a pass begun for the last episode can land after the next one has
    /// started and hand it the previous pane's pixels, or clear a `refreshing` flag it does not own.
    private var generation = 0

    /// What the pane said, last time anybody looked — and a fresh look started when that is stale.
    ///
    /// Returns an empty array rather than a stale one whenever the reading was taken of a different
    /// window or for a different capability: those are not old answers, they are answers to a
    /// different question, and the boxes inside them would land on real rows in the wrong place.
    ///
    /// Age alone never withholds a reading, it only triggers the refresh. Blinking the arrow off
    /// every `refreshInterval` while a perfectly good pass is running would be the flapping
    /// `SpotlightHysteresis` exists to stop, one layer lower and self-inflicted.
    ///
    /// **The schedule is on the attempt, not on the answer.** The obvious shape — refresh whenever
    /// the *reading* is missing or stale — has no schedule at all in the case that matters most: a
    /// process without Screen Recording never gets a reading, so "missing" is permanent, and this
    /// would launch a pass on every 40 ms tick of the whole Accessibility step. Cheap passes (they
    /// stop at `CGPreflightScreenCaptureAccess`) but 25 tasks a second, forever, to keep answering the
    /// same no.
    func labels(for capability: Capability, of window: CGRect, now: ContinuousClock.Instant = .now)
        -> [RecognizedLabel]
    {
        lock.lock()
        let held = reading
        let matches = held.map { $0.capability == capability && $0.window == window } ?? false
        let due = lastAttempt.map { $0.duration(to: now) >= Self.refreshInterval } ?? true
        // A question we have no answer to at all is worth asking as soon as the schedule allows; one
        // we have a current answer to is worth re-asking only when that answer has aged out.
        let shouldRefresh = due && !refreshing
        if shouldRefresh {
            refreshing = true
            lastAttempt = now
            passes += 1
        }
        let announce = shouldRefresh && !announced
        if announce { announced = true }
        let era = generation
        lock.unlock()

        if shouldRefresh { start(for: capability, announcing: announce, era: era) }
        return matches ? (held?.labels ?? []) : []
    }

    /// Drops whatever was read. Called when the overlay goes down, so the next episode can never open
    /// on the last one's pixels — the capability key already refuses that, and this is what keeps the
    /// refusal from depending on two capabilities being different.
    ///
    /// The schedule is dropped with it: a new episode is entitled to look immediately rather than wait
    /// out the tail of the last one's interval.
    func forget() {
        lock.lock()
        reading = nil
        lastAttempt = nil
        announced = false
        passes = 0
        refreshing = false
        generation += 1
        lock.unlock()
    }

    /// How many capture-and-recognise passes this object has started. The only thing that costs
    /// anything here, and therefore the only thing worth counting.
    var passesStarted: Int {
        lock.lock()
        defer { lock.unlock() }
        return passes
    }

    /// Seeds a reading directly. **Tests only** — there is no other way to exercise the hand-off from
    /// a pass to a caller without a live System Settings and a real Screen Recording grant.
    ///
    /// Sets the schedule too, because a reading that exists is a pass that happened; leaving the two
    /// apart would let a test observe a state the live object cannot be in.
    func remember(_ labels: [RecognizedLabel], for capability: Capability, of window: CGRect,
                  takenAt: ContinuousClock.Instant = .now) {
        lock.lock()
        reading = Reading(capability: capability, window: window, labels: labels, takenAt: takenAt)
        lastAttempt = takenAt
        lock.unlock()
    }

    private func start(for capability: Capability, announcing first: Bool, era: Int) {
        if first {
            // Once per episode, not once per pass. `forget()` is what makes "first" mean the first of
            // an episode. A branch that changed provider is worth recording; a branch that records it
            // every 800 ms for the length of a permission step is a log, and a log nobody can read is
            // worse than the counter it replaced.
            ContextTelemetry.recordFallback(
                area: .settings, from: "settings-accessibility-walk", to: "settings-pixel-sighting",
                reason: "ax-tree-unreadable", outcome: .retried)
        }
        Task.detached(priority: .utility) { [weak self] in
            let read = await SettingsPaneReader.read()
            self?.finish(read, for: capability, era: era)
        }
    }

    /// The end of one pass. Synchronous and separate from the task that awaits the pass, because a
    /// lock held across a suspension point is a lock that can be released on a different thread than
    /// took it — which `NSLock` does not survive, and which Swift 6 refuses outright.
    ///
    /// A pass that read nothing leaves the previous reading alone rather than clearing it. The window
    /// server refuses a capture for ordinary, momentary reasons — a Space switch, a display waking —
    /// and throwing away a good answer on the first of them is the flapping this type exists to avoid.
    private func finish(
        _ read: (window: CGRect, labels: [RecognizedLabel])?, for capability: Capability, era: Int
    ) {
        lock.lock()
        defer { lock.unlock() }
        // Started before the last `forget()`, so it belongs to an episode that is over. Its pixels are
        // of a pane nobody is looking at any more, and its `refreshing` is not this episode's to clear.
        guard era == generation else { return }
        if let read {
            reading = Reading(
                capability: capability, window: read.window, labels: read.labels, takenAt: .now)
        }
        refreshing = false
    }
}
