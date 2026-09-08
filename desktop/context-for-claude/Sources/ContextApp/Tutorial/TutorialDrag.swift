import AppKit

/// Whether the user has really dragged, decided from the scroll events themselves.
///
/// Split out from the monitor for the same reason `ModifierDoubleTap` is split out from
/// `GlobalShortcuts`: "they genuinely swiped" is the whole feature, and it is the part that can be
/// wrong in ways no amount of clicking around reveals — there is no trackpad in a test process.
/// Feeding it synthetic samples is the only way to know that a light two-finger flick satisfies it,
/// that momentum still counts, that a notched wheel counts, and that a hand resting on the pad does
/// not.
///
/// ## What this deliberately does *not* do
///
/// The timeline beat used to ask for this gesture and listen for nothing at all, so every one of
/// these was a way for the fix to fail in turn. None of them is a rule here:
///
/// - **No phase filter.** A trackpad swipe arrives as `.began`/`.changed`/`.ended` and then as a
///   tail of momentum events whose `phase` is empty and whose `momentumPhase` is not; a notched
///   wheel arrives with *neither* set. Requiring a phase is how a recogniser ends up ignoring the
///   half of the gesture the user can still see moving.
/// - **No direction.** The gate accepts left and right. Which way is "back" depends on the user's
///   own natural-scrolling setting, which this app does not get to assume, and a beat that rejects
///   half of a real gesture on a preference we cannot read is the tutorial being pedantic at
///   someone who did exactly what it asked.
/// - **No trackpad requirement.** A mouse wheel is a legitimate way to move the timeline, so
///   `hasPreciseScrollingDeltas` scales the numbers rather than rejecting the event.
struct TutorialDrag {

    /// Points of travel a drag has to cover before it counts.
    ///
    /// Deliberately small. One natural two-finger flick across a trackpad reports several hundred
    /// points, so this is met inside the first tenth of the gesture and cannot be met by a hand
    /// resting on the pad. The failure it exists to avoid is a threshold tuned so tight that a real
    /// gesture reads as noise.
    static let travelRequired: Double = 40

    /// A line of a notched wheel, in points. Non-precise deltas are counted in *lines*, so four real
    /// notches report about four units and would never clear a threshold measured in points.
    static let pointsPerLine: Double = 10

    /// How long a stretch of silence forgets what has been travelled so far. Long enough that a
    /// flick, its momentum, and a second flick are one continuous effort; short enough that two
    /// stray twitches minutes apart never add up to a gesture.
    static let idleGap: Double = 2.0

    /// One `scrollWheel` event, reduced to what the rules need.
    struct Sample: Equatable {
        let deltaX: Double
        let deltaY: Double
        /// `NSEvent.hasPreciseScrollingDeltas`: true for a trackpad or Magic Mouse, false for a
        /// notched wheel.
        let isPrecise: Bool
        /// Monotonic, from `NSEvent.timestamp`.
        let at: Double

        init(deltaX: Double, deltaY: Double, isPrecise: Bool, at: Double) {
            self.deltaX = deltaX
            self.deltaY = deltaY
            self.isPrecise = isPrecise
            self.at = at
        }

        init(_ event: NSEvent) {
            self.init(
                deltaX: Double(event.scrollingDeltaX),
                deltaY: Double(event.scrollingDeltaY),
                isPrecise: event.hasPreciseScrollingDeltas,
                at: event.timestamp)
        }

        /// Points this one event travelled, in whichever axis dominates.
        ///
        /// `max` rather than a sum, so a diagonal drag is not counted twice — the user moved once.
        var travel: Double {
            let raw = max(abs(deltaX), abs(deltaY))
            return isPrecise ? raw : raw * TutorialDrag.pointsPerLine
        }
    }

    /// Points travelled in the current stretch. Exposed for the tests that assert the idle reset.
    private(set) var travelled: Double = 0
    private var lastAt: Double?

    /// Feeds one event in.
    ///
    /// - Returns: `true` exactly once — on the event that takes the accumulated travel past the bar.
    ///   Everything after that is `false`, so a caller cannot double-fire on the momentum tail.
    mutating func received(_ sample: Sample) -> Bool {
        let travel = sample.travel
        guard travel > 0 else { return false }
        if let lastAt, sample.at - lastAt > Self.idleGap { travelled = 0 }
        lastAt = sample.at
        let before = travelled
        travelled += travel
        return before < Self.travelRequired && travelled >= Self.travelRequired
    }

    mutating func reset() {
        travelled = 0
        lastAt = nil
    }
}

// MARK: - The live watcher

/// Watches for a real drag over this app's own windows, for exactly as long as a step is asking for
/// one.
///
/// A **local** monitor rather than a global one, and that is the whole delivery decision: the beat
/// asks the user to drag on the timeline this app has just put in front of them, and a local monitor
/// sees every scroll event AppKit delivers to our own windows — the timeline, its track, and the
/// card itself. A global monitor would be asking macOS for Accessibility in order to observe events
/// that are already ours.
///
/// The handler returns the event unchanged. Nothing here consumes anything: the track's own
/// `scrollWheel` still runs, so the same gesture that satisfies the beat is the gesture that moves
/// the timeline.
@MainActor
final class TutorialDragWatcher {
    static let shared = TutorialDragWatcher()

    private var monitor: Any?
    private var drag = TutorialDrag()
    private var onTravelled: (() -> Void)?

    /// Starts watching. Idempotent: a second start replaces the first rather than stacking monitors.
    func start(_ onTravelled: @escaping () -> Void) {
        stop()
        drag.reset()
        self.onTravelled = onTravelled
        monitor = NSEvent.addLocalMonitorForEvents(matching: .scrollWheel) { event in
            MainActor.assumeIsolated { TutorialDragWatcher.shared.received(event) }
            return event
        }
    }

    func stop() {
        if let monitor { NSEvent.removeMonitor(monitor) }
        monitor = nil
        onTravelled = nil
        drag.reset()
    }

    private func received(_ event: NSEvent) {
        guard drag.received(TutorialDrag.Sample(event)) else { return }
        let announce = onTravelled
        // Stopped before the callback: the beat has what it asked for, and a monitor left running
        // over the rest of the tutorial would be this app watching scroll events for no reason.
        stop()
        announce?()
    }
}
