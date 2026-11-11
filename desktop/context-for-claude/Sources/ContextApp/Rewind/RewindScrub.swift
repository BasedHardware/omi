import ContextCore
import Foundation

/// Where the playhead sits **between** two captures, and what the stage should draw there.
///
/// **Why this exists.** The capture writes one frame every three seconds, and the timeline used to
/// hold nothing finer than that: the playhead was an *index* into the frame array, so the only
/// positions that existed were the captures themselves and every scrub step replaced one screenshot
/// with the next in a single frame of animation. That is what "flipping through a photo album" is —
/// not slowness, but the absence of anything at all between two stills.
///
/// There genuinely is nothing between them, and nothing here pretends otherwise. Three seconds of a
/// screen are not recoverable from its endpoints. What this does instead is **cross-dissolve two
/// real captures** while the playhead travels from one to the other, at the weight the playhead's own
/// position implies. Every pixel on screen was photographed; only its opacity is computed. No
/// intermediate frame is synthesised and no motion is estimated — the difference between blending
/// evidence and inventing it.
///
/// All of it is decidable without a screen: a position and an array of capture instants produce a
/// number. That is why it lives here rather than inside the model or the view, the same reason
/// `RewindZoom` does.
enum RewindScrub {

    // MARK: - The shape of a dissolve

    /// Where the dissolve starts and ends, as a fraction of the interval between two captures.
    ///
    /// Deliberately not 0→1. A dissolve that ran the whole interval would mean a playhead resting
    /// anywhere except exactly on a capture holds a permanent double exposure of two different
    /// screens — an image that never existed, presented as steadily as one that did, which is a worse
    /// lie than a hard cut. Holding the first and last third at full weight makes the dissolve a
    /// *transition* rather than a state: most resting positions show a single genuine capture, and
    /// the fade happens as the playhead crosses the middle.
    static let blendStart = 0.35
    static let blendEnd = 0.65

    /// The widest gap between two captures that still counts as "adjacent", in seconds.
    ///
    /// The tick is three seconds; six is one dropped capture and still reads as consecutive. Past
    /// eight the two pictures are not neighbours in any sense a dissolve could express — the machine
    /// slept, the app was excluded, the user was away — and fading one into the other would narrate a
    /// continuity that did not happen. Those cut instead, at the midpoint, which is exactly where
    /// `Array<RewindFrame>.nearestIndex(to:)` already switches from one to the other.
    static let maximumBlendGap: Double = 8

    /// The two captures a continuous playhead sits between, and how far the dissolve has travelled.
    struct Blend: Equatable {
        /// The capture at or before the playhead — the layer drawn underneath.
        let base: Int
        /// The capture after it. Nil at either end of the day, and across a gap too wide to dissolve.
        let next: Int?
        /// 0 shows `base` alone, 1 shows `next` alone.
        let weight: Double

        /// The capture the playhead is *on*, which is the one the timestamp pill, the segment colour
        /// and Live Text all speak for.
        ///
        /// Ties go to the earlier capture, matching `nearestIndex(to:)` exactly. The two rules must
        /// agree or the picture and the clock above it name different moments.
        var dominant: Int { weight > 0.5 ? (next ?? base) : base }
    }

    /// Where `instant` sits in `frames`, as a pair of real captures and a weight between them.
    ///
    /// Nil only when there is nothing showable at all.
    static func blend(at instant: Double, in frames: [RewindFrame]) -> Blend? {
        guard let first = frames.first, let last = frames.last else { return nil }
        // Outside the captured range there is nothing to be between. Clamping rather than
        // extrapolating: the day's first frame is the oldest thing that exists, and fading it into
        // the void would be drawing a moment that was never captured.
        guard instant > first.capturedAt else { return Blend(base: 0, next: nil, weight: 0) }
        guard instant < last.capturedAt else {
            return Blend(base: frames.count - 1, next: nil, weight: 0)
        }

        // The first capture strictly after the playhead; its predecessor is the one at or before it.
        // Binary search for the same reason `nearestIndex` uses one — this runs on every pointer move
        // of a drag, over a day that can hold thousands of frames.
        var low = 0
        var high = frames.count - 1
        while low < high {
            let mid = low + (high - low) / 2
            if frames[mid].capturedAt <= instant { low = mid + 1 } else { high = mid }
        }
        let after = low
        let before = low - 1

        let gap = frames[after].capturedAt - frames[before].capturedAt
        // Two rows stamped at the same instant is a clock fault, not an interval; there is no
        // fraction to compute across a zero.
        guard gap > 0 else { return Blend(base: before, next: nil, weight: 0) }

        let fraction = (instant - frames[before].capturedAt) / gap
        guard gap <= maximumBlendGap else {
            return Blend(base: fraction <= 0.5 ? before : after, next: nil, weight: 0)
        }
        return Blend(base: before, next: after, weight: ramp(fraction))
    }

    /// The dissolve's curve across one interval: flat, eased, flat.
    ///
    /// Smoothstep across the middle band rather than a straight line, so the fade has no corner where
    /// it starts and stops. A linear ramp switching on at 35% is visible *as a switch* — the eye
    /// catches the discontinuity in the rate, not the opacity — which is the same complaint one level
    /// down from the one this file exists to fix.
    static func ramp(_ fraction: Double) -> Double {
        let clamped = min(max(fraction, blendStart), blendEnd)
        let t = (clamped - blendStart) / (blendEnd - blendStart)
        return t * t * (3 - 2 * t)
    }

    // MARK: - What is actually drawn

    /// The two layers the stage puts up, given which of the captures are already decoded.
    struct Layers: Equatable {
        /// The picture drawn underneath. Nil when neither capture is decoded yet, which is the
        /// caller's signal to keep whatever is already on screen rather than blanking it.
        let base: Int?
        /// The picture fading in over it, or nil when there is no dissolve to draw.
        let over: Int?
        /// `over`'s opacity. Zero whenever `over` is nil.
        let weight: Double
    }

    /// **The dissolve is opportunistic, and that is the whole reason it costs nothing.**
    ///
    /// It engages only when both real captures are already in memory. Waiting on a decode to start a
    /// fade would put a stall in the middle of the very gesture this exists to smooth; and at a wide
    /// zoom, where one pixel of drag crosses twenty captures, it would double the decode load for a
    /// fade nobody could perceive. Degrading to a cut costs nothing and is never *wrong* — a cut is
    /// what the timeline did on every single step before any of this existed.
    static func layers(for blend: Blend, baseIsDecoded: Bool, nextIsDecoded: Bool) -> Layers {
        if let next = blend.next, blend.weight > 0, baseIsDecoded, nextIsDecoded {
            return Layers(base: blend.base, over: next, weight: blend.weight)
        }
        if baseIsDecoded { return Layers(base: blend.base, over: nil, weight: 0) }
        // The capture under the playhead is not decoded but its neighbour is. Showing the real
        // neighbour beats showing nothing: it is never more than one capture — three seconds — away,
        // and it is a photograph rather than a placeholder.
        if let next = blend.next, nextIsDecoded { return Layers(base: next, over: nil, weight: 0) }
        return Layers(base: nil, over: nil, weight: 0)
    }

    // MARK: - Prefetch

    /// Captures decoded either side of a playhead that is standing still.
    ///
    /// Five either side is ~30 seconds of capture at the 3 s tick, comfortably more than a drag
    /// covers between two frames being asked for.
    static let prefetchRadius = 5

    /// …and how the same budget is aimed once the playhead is moving: ahead, and behind.
    ///
    /// The count is identical — eleven captures either way — so the memory the decoded-frame budget
    /// is sized against does not change. What changes is which side of the playhead they sit on. A
    /// symmetric window spends half its decodes on captures the scrub has already gone past, which is
    /// exactly backwards while it is moving. The trailing two stay because a scrub reverses
    /// constantly: the user overshoots and comes back, and a purely one-sided window makes going back
    /// feel broken while going forward feels fine.
    static let prefetchLead = 8
    static let prefetchTrail = 2

    /// The most captures `prefetchWindow` can ever name, which is what the decoded-frame budget in
    /// `FrameLoader.memoryBudgetBytes` is sized against.
    static let prefetchWindowWidth = prefetchLead + prefetchTrail + 1

    /// The captures worth decoding around `index`, aimed where the playhead is going.
    ///
    /// - Parameter direction: the sign of the last movement; 0 when the playhead is at rest.
    static func prefetchWindow(around index: Int, direction: Int, count: Int) -> ClosedRange<Int>? {
        guard count > 0, index >= 0, index < count else { return nil }
        let lead: Int
        let trail: Int
        if direction > 0 {
            lead = prefetchLead
            trail = prefetchTrail
        } else if direction < 0 {
            lead = prefetchTrail
            trail = prefetchLead
        } else {
            lead = prefetchRadius
            trail = prefetchRadius
        }
        return max(0, index - trail)...min(count - 1, index + lead)
    }
}
