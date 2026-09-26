import Foundation

/// The tail of a scrub: a short coast after the fingers lift, then a settle onto a real capture.
///
/// **Why a scrub has to end on a capture.** The dissolve in `RewindScrub` is honest only while it is
/// a *transition*. A playhead left parked halfway between two captures holds a permanent 50/50
/// composite of two different screens on the stage — a picture that never existed, presented exactly
/// as steadily as one that did. Coming to rest on a capture is what keeps the resting state a
/// photograph, and it is why every gesture ends here.
///
/// **Why it coasts first.** A scroll that stops on its last event stops dead, and nothing else on the
/// machine does. macOS already sends the inertia: a trackpad flick keeps delivering scroll events
/// with decaying deltas after the fingers leave. The timeline used to throw every one of them away —
/// `RewindModel.travel(by:)` re-derived its position from the *snapped* frame each time, so any delta
/// smaller than half a capture interval resolved back to the same frame and vanished, and a momentum
/// tail is nothing but deltas decaying towards zero. So most of the inertia here is the platform's,
/// recovered rather than invented. This adds only the short overshoot that carries the last of the
/// flick's speed past the final event, and the ease that lands it.
///
/// Pure arithmetic on purpose: a settle proved by sleeping is a test that fails on a loaded machine.
struct RewindGlide: Equatable {

    /// How long the playhead keeps travelling at the speed it was released at.
    ///
    /// Short. This is the overshoot *past* the system's own momentum, not a replacement for it —
    /// long enough that a flick does not stop on a hard edge, short enough that the playhead never
    /// runs away from where the user let go.
    static let coastSeconds: Double = 0.09

    /// The settle's duration bounds. A settle is a landing, not a journey: under a tenth of a second
    /// for a nudge, and still comfortably under a third when it has most of the visible track to
    /// cross, because anything slower reads as the timeline deciding where to go on its own.
    static let minimumSettle: Double = 0.09
    static let maximumSettle: Double = 0.26

    /// Below this the settle is a move nobody can see, and snapping costs less than animating it.
    static let negligibleDistance: Double = 0.001

    let from: Double
    let to: Double
    let duration: Double

    /// Where a released scrub coasts to before it starts settling.
    ///
    /// - Parameter velocity: timeline-seconds per second of wall clock. It is derived from pixels of
    ///   finger travel through the track's span, so it is already zoom-relative: the same flick
    ///   covers the same distance on screen and correspondingly less *time* when zoomed in.
    static func projectedRest(from: Double, velocity: Double) -> Double {
        from + velocity * coastSeconds
    }

    /// - Parameter visibleSpan: the seconds of timeline the track is showing, so a settle that
    ///   crosses a lot of the track takes visibly longer than one that nudges a few pixels — and does
    ///   so identically at every zoom, because both are measured against the same width of screen.
    ///   A fixed duration would make the same on-screen distance feel like a crawl zoomed in and a
    ///   teleport zoomed out.
    ///
    /// Fails when there is nothing to travel, which the caller reads as "already there".
    init?(from: Double, to: Double, visibleSpan: Double) {
        guard abs(to - from) > Self.negligibleDistance else { return nil }
        self.from = from
        self.to = to
        let fraction = min(1, abs(to - from) / max(1, visibleSpan))
        self.duration = Self.minimumSettle + fraction * (Self.maximumSettle - Self.minimumSettle)
    }

    /// Where the playhead is `elapsed` seconds into the settle.
    ///
    /// Ease-out cubic: fast off the mark and slow into the frame, which is what coming to rest looks
    /// like. An ease-*in*-out would accelerate again after the user had already stopped, which reads
    /// as the timeline taking over rather than as momentum running out.
    func instant(atElapsed elapsed: Double) -> Double {
        guard duration > 0 else { return to }
        let t = min(max(elapsed / duration, 0), 1)
        let eased = 1 - pow(1 - t, 3)
        return from + (to - from) * eased
    }

    func isFinished(atElapsed elapsed: Double) -> Bool { elapsed >= duration }
}
