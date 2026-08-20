import Foundation

/// The arithmetic behind "zoom the timeline", as pure values.
///
/// It lives outside `RewindModel` for two reasons.
///
/// **There are two ways to drive the same zoom.** The magnifier buttons in the control cluster and a
/// trackpad pinch over the track are the same feature reached two ways, and the way two such paths go
/// wrong is not that one of them breaks — it is that they quietly disagree, about the bounds, or about
/// what the zoom is anchored on, so the buttons and the fingers leave the track in different states
/// and neither is reproducible. Everything below is the one implementation both of them call, and
/// `RewindModel` exposes exactly one mutation point on top of it.
///
/// **All of it is decidable without a screen.** Given a span, an anchor and the day, the answer is a
/// number: whether the anchored moment stayed under the pointer, and whether the span stopped at its
/// bound, are properties a test can check exactly. The parts that need a window — routing the AppKit
/// gesture, drawing the result — are kept as thin as they can be over this.
enum RewindZoom {

    // MARK: - Bounds

    /// The narrowest the track may be zoomed, in seconds.
    ///
    /// Two minutes is about forty frames at the 3 s capture tick. Below that the track is mostly one
    /// segment, the badge row cannot pack another icon in, and the zoom has nothing left to reveal —
    /// it would only be making the same picture wider.
    static let minimumSpan: Double = 120

    /// The widest, in seconds.
    ///
    /// A full day, because the track is bounded by the day that is loaded and going wider is what the
    /// date picker is for. It is a *request* rather than the final word: `window(for:spanBounds:within:)`
    /// narrows it to the loaded day, which is 23 or 25 hours whenever the clocks have just changed.
    static let maximumSpan: Double = 24 * 3600

    // MARK: - Values

    /// A visible stretch of the track: where it starts, and how much time it shows.
    struct Window: Equatable {
        var start: Double
        var span: Double

        var end: Double { start + span }
    }

    /// What the track is being asked to show — a span, plus the promise that goes with it.
    ///
    /// The anchor and its fraction are carried together with the span because they are not optional
    /// decoration: a span without them says how much time to show but not *which* time, and the
    /// obvious answer ("keep the start") slides the whole day sideways under the pointer, which is the
    /// version of zooming that feels broken. Making the three travel as one value is what stops a
    /// future call site from supplying a span and forgetting the rest.
    struct Target: Equatable {
        /// How much time the track should show, in seconds. Clamped when the window is computed.
        let span: Double
        /// The moment that must not move on screen while the span changes.
        let anchor: Double
        /// Where that moment sits across the track's width: 0 at the left edge, 1 at the right.
        let fraction: Double
    }

    // MARK: - Arithmetic

    /// Where `instant` sits across the track's width: 0 at the left edge, 1 at the right.
    ///
    /// Clamped, because an anchor that is currently off-screen has no on-screen position to preserve.
    /// Feeding its out-of-range fraction back into `window(for:…)` would fling the window further away
    /// from the anchor rather than bringing it into view — a fraction of 3.5 means "keep this moment
    /// two and a half track-widths off the right edge", which is never what the caller meant.
    static func fraction(of instant: Double, in window: Window) -> Double {
        guard window.span > 0 else { return 0.5 }
        return min(max(0, (instant - window.start) / window.span), 1)
    }

    /// The window that honours `target` as closely as the bounds and the loaded day allow.
    ///
    /// The *current* window is deliberately not an input. `start = anchor - fraction × span` is
    /// everything there is to say, and computing it from scratch each time is what makes a long pinch
    /// exact: a hundred events all recompute the same equation from the same anchor rather than
    /// applying a hundred corrections to a running value, so there is no accumulated drift to see.
    static func window(
        for target: Target,
        spanBounds: ClosedRange<Double>,
        within day: ClosedRange<Double>
    ) -> Window {
        let dayLength = day.upperBound - day.lowerBound

        // Three ceilings, and they mean different things: what the caller asked for, what the zoom
        // permits, and what the day contains. The day wins over both, because a track that showed a
        // wider window than the day it loaded would be drawing hours of time the frames in memory
        // cannot possibly cover — empty channel presented as if it were captured and empty.
        var span = min(max(target.span, spanBounds.lowerBound), spanBounds.upperBound)
        span = min(span, dayLength)

        // A day with no length at all is not a state the model produces, but the arithmetic below
        // divides the day by this and a zero would make every position meaningless. Show the day.
        guard span > 0 else { return Window(start: day.lowerBound, span: max(0, dayLength)) }

        // Put the anchor back where it was on screen, then slide the whole window inside the day if
        // that pushed it out. Sliding rather than re-anchoring is the deliberate part: within a few
        // minutes of midnight the anchor genuinely *cannot* stay under the pointer, because there is
        // no time on the far side to show, and filling the gap with real capture beats holding the
        // anchor still over blank track.
        let placed = target.anchor - target.fraction * span
        let start = min(max(day.lowerBound, placed), day.upperBound - span)
        return Window(start: start, span: span)
    }
}

/// One continuous trackpad pinch over the track, accumulated.
///
/// **AppKit hands a pinch over as a stream of deltas, not as a scale.** `NSEvent.magnification` is the
/// *change* in magnification since the previous event of the same gesture — a hundredth or two at a
/// time — where SwiftUI's magnification gestures report the total scale since the gesture began.
/// Confusing the two is the classic bug in both directions: treat a cumulative scale as a delta and a
/// slow pinch runs away exponentially; treat a delta stream as absolute and the zoom barely moves.
/// This type is the one place that decision is made, and it makes it once.
///
/// The anchor and the starting span are captured when the fingers go down and never re-read:
///
/// - The **anchor** is fixed because fingers drift during a pinch. Re-reading the pointer every event
///   would let the moment being zoomed on wander across the track while the user believes they are
///   holding still, which reads as the timeline sliding out from under them.
/// - The **starting span** is fixed for a subtler reason. The track is a SwiftUI-hosted view: applying
///   a zoom publishes a new span on the model, which comes straight back down through `updateNSView`
///   and overwrites this view's `trackSpan` mid-gesture. A pinch that multiplied *that* value on the
///   next event would be squaring its own output — the runaway above, arriving by the back door. It
///   also makes total finger travel mean total zoom: spread and close back to where you started and
///   you are on exactly the span you started on.
///
/// The cumulative magnification is clamped to the range that keeps the span inside its bounds, rather
/// than clamping only the span it produces. That is the difference between "stops at the bound" and
/// "ratchets": if the overshoot were stored, a user who keeps pinching after the track has bottomed
/// out at two minutes would have to pay all of it back before the reverse pinch did anything at all,
/// and the control would feel stuck for no visible reason.
struct RewindPinch: Equatable {

    /// The smallest factor a single event may contribute.
    ///
    /// `1 + magnification` is the event's factor, and the API's type permits a delta of −1 or worse
    /// even though a trackpad does not produce one. Unfloored, one such event multiplies the
    /// accumulator by zero or flips its sign and strands the gesture with no way back.
    private static let minimumStep: Double = 0.1

    /// The moment that must stay under the pointer for the whole gesture.
    let anchor: Double
    /// Where that moment sits across the track's width, 0 at the left edge and 1 at the right.
    let fraction: Double
    /// The span the track was showing when the fingers went down.
    let startSpan: Double
    /// The range the span may move within, from the model — the loaded day narrows it.
    let spanBounds: ClosedRange<Double>

    /// Cumulative magnification since the gesture began: 1 at rest, above 1 once the fingers have
    /// spread — which zooms *in*, and therefore shrinks the span.
    private(set) var magnification: Double = 1

    init(anchor: Double, fraction: Double, startSpan: Double, spanBounds: ClosedRange<Double>) {
        // Normalised on the way in so the bound arithmetic in `advance` cannot divide by zero or
        // start outside the range it exists to enforce. One second is the smallest span that means
        // anything on a track of screenshots captured every three.
        let floor = max(1, spanBounds.lowerBound)
        let ceiling = max(floor, spanBounds.upperBound)
        self.spanBounds = floor...ceiling
        self.startSpan = min(max(startSpan, floor), ceiling)
        self.anchor = anchor
        self.fraction = min(max(0, fraction), 1)
    }

    /// Folds one `NSEvent.magnification` delta in and returns what the track should now show.
    mutating func advance(by delta: Double) -> RewindZoom.Target {
        // The magnification that would put the span exactly on each bound. Clamping here rather than
        // on the resulting span is what keeps the gesture reversible at the ends — see the note above.
        let atNarrowest = startSpan / spanBounds.lowerBound
        let atWidest = startSpan / spanBounds.upperBound
        magnification = min(max(magnification * max(Self.minimumStep, 1 + delta), atWidest), atNarrowest)
        return target
    }

    /// What this gesture is currently asking for, without advancing it.
    var target: RewindZoom.Target {
        RewindZoom.Target(span: startSpan / magnification, anchor: anchor, fraction: fraction)
    }
}
