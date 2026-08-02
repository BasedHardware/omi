import AppKit
import Combine
import Foundation
import SwiftUI

/// The nine-blob gradient field every onboarding step floats over.
///
///     Backdrop(working: engine.isThinking, settled: step.hasSettled) {
///         StepView()
///     }
///
/// - `working` runs the 14 s drift orbit; when it goes false the orbit comes to rest.
/// - `settled` hollows the centre of the field over 280 ms so headline copy stays legible.
///
/// Every value the field draws is a pure function of a `TimelineView` clock plus a handful of
/// ramp anchors, so a frame costs arithmetic and no view-graph churn. There is exactly one
/// `withAnimation`-shaped thing in this file — `Ramp` — and it is plain interpolation, not a
/// SwiftUI animation.
struct Backdrop<Content: View>: View {
    private let working: Bool
    private let settled: Bool
    private let content: Content

    init(working: Bool, settled: Bool, @ViewBuilder content: () -> Content) {
        self.working = working
        self.settled = settled
        self.content = content()
    }

    /// When the field appeared; anchors the fade-in and the rise.
    @State private var appearedAt: Date?
    /// 0 → 1 as the step settles. Feeds the centre stop of the mask.
    @State private var clarityRamp = Ramp(value: 0)
    /// Envelope on the drift orbit. See `blob(_:size:...)` for why the orbit is not switched
    /// on and off directly.
    @State private var driftRamp = Ramp(value: 0)
    /// True once nothing is left to animate, which pauses the timeline entirely.
    @State private var isQuiescent = false
    /// Bumped when the user flips Reduce Motion. `InkReduceMotion.isEnabled` is a plain system
    /// read, not observable, and this view outlives every step — without this, someone who turns
    /// Reduce Motion on because the drift is making them ill would keep watching it drift.
    @State private var reduceMotionEpoch = 0

    var body: some View {
        ZStack {
            // A sheet under the wash. The surface takes almost none of its brightness from the
            // desktop behind it: without a floor of its own, type would sit on whatever the user
            // happens to have open. This is the sheet — and it fades on the same falloff as
            // everything else, so it adds substance without adding an edge.
            ZStack {
                scrimLayer
                fieldLayer
            }
            // One ellipse over the whole painted surface. Every layer under it — the sheet floor
            // and the nine blobs — is rectangular on its own; this is the only thing standing
            // between that and a visible box on the desktop, so it masks the composite rather than
            // each layer separately. Alpha reaches zero before the frame edge, so there is nothing
            // left to clip at the corners.
            .mask {
                EllipticalGradient(
                    stops: [
                        .init(color: .white, location: 0),
                        .init(color: .white, location: 0.52),
                        .init(color: .white.opacity(0.72), location: 0.78),
                        .init(color: .white.opacity(0.26), location: 0.92),
                        .init(color: .white.opacity(0), location: 1),
                    ],
                    center: .center,
                    startRadiusFraction: 0,
                    endRadiusFraction: 0.5
                )
            }

            content
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onAppear {
            if appearedAt == nil { appearedAt = Date() }
            clarityRamp.retarget(to: settled ? 1 : 0, at: Date(), over: InkMotion.settle)
            driftRamp.retarget(to: working ? 1 : 0, at: Date(), over: Spec.driftEnvelope)
        }
        .onChange(of: settled) { _, isSettled in
            clarityRamp.retarget(to: isSettled ? 1 : 0, at: Date(), over: InkMotion.settle)
        }
        .onChange(of: working) { _, isWorking in
            driftRamp.retarget(to: isWorking ? 1 : 0, at: Date(), over: Spec.driftEnvelope)
        }
        .onReceive(
            NSWorkspace.shared.notificationCenter.publisher(for: InkReduceMotion.didChangeNotification)
        ) { _ in
            reduceMotionEpoch &+= 1
        }
        .task(id: MotionKey(working: working, settled: settled)) {
            // The timeline only needs to tick while something is still moving. A static step
            // would otherwise re-render a full-screen blurred gradient forever.
            isQuiescent = false
            guard !InkReduceMotion.isEnabled, !working else { return }
            try? await Task.sleep(for: .seconds(Spec.quiesceAfter))
            guard !Task.isCancelled else { return }
            isQuiescent = true
        }
    }

    // MARK: - The field

    /// The sheet floor, on the same elliptical falloff as the field so it dissolves rather than
    /// ends.
    private var scrimLayer: some View {
        // Flat on purpose: the composite ellipse above shapes it. Not fully opaque — the last few
        // per cent let the desktop through as a tint, which is what keeps the oval reading as a
        // sheet lying on the screen rather than a window pasted over it. Still opaque enough that
        // `Ink.primary` type keeps its full contrast over any desktop, in either appearance.
        Ink.surface.opacity(0.985)
            .allowsHitTesting(false)
    }

    private var fieldLayer: some View {
        GeometryReader { geo in
            if InkReduceMotion.isEnabled {
                // Reduce Motion: no fade, no rise, no drift — the resolved state, immediately.
                field(
                    size: geo.size,
                    fade: Spec.peakOpacity,
                    rise: 1,
                    driftSeconds: 0,
                    driftAmplitude: 0,
                    clarity: settled ? 1 : 0
                )
            } else {
                // Only the blobs live inside the TimelineView. Putting `content` in here would
                // re-evaluate the whole onboarding step on every display frame. 60 Hz is the cap
                // because nobody can see a 24σ blur resolve faster than that, and ProMotion would
                // otherwise double the cost for free.
                TimelineView(.animation(minimumInterval: 1.0 / 60.0, paused: isQuiescent)) { ctx in
                    field(size: geo.size, now: ctx.date)
                }
            }
        }
        .allowsHitTesting(false)
    }

    private func field(size: CGSize, now: Date) -> some View {
        let elapsed = appearedAt.map { max(0, now.timeIntervalSince($0)) } ?? 0
        return field(
            size: size,
            fade: easeOut(clamp01(elapsed / InkMotion.backdropFadeIn)) * Spec.peakOpacity,
            rise: easeOut(clamp01(elapsed / InkMotion.backdropRise)),
            driftSeconds: elapsed,
            driftAmplitude: driftRamp.value(at: now),
            clarity: clarityRamp.value(at: now)
        )
    }

    private func field(
        size: CGSize,
        fade: Double,
        rise: Double,
        driftSeconds: Double,
        driftAmplitude amplitude: Double,
        clarity: Double
    ) -> some View {
        // Deliberately no `.drawingGroup()`. `.blur(radius:)` already forces an offscreen pass,
        // and while `working` the blob geometry changes every frame — a flattened texture would
        // be invalidated and re-rasterised each frame anyway, so the flatten buys nothing and
        // costs an extra copy. It also rasterises at a fixed scale, which bands a 24σ blur
        // visibly on a 5K frame. Not benchmarked here: the package does not build until every
        // onboarding file lands. If a profile ever shows the nine fills dominating (Instruments →
        // Core Animation, `working` true, full `visibleFrame` window), the cheaper win is fewer
        // and larger blobs, not caching a layer that changes every frame.
        ZStack {
            ForEach(0..<Ink.backdropBlobs.count, id: \.self) { index in
                blob(
                    index,
                    size: size,
                    rise: rise,
                    driftSeconds: driftSeconds,
                    amplitude: amplitude
                )
            }
        }
        .frame(width: size.width, height: size.height)
        .blur(radius: Spec.blurSigma)
        .mask { hollow(clarity: clarity) }
        .opacity(fade)
    }

    private func blob(
        _ index: Int,
        size: CGSize,
        rise: Double,
        driftSeconds: Double,
        amplitude: Double
    ) -> some View {
        let spec = Ink.backdropBlobs[index]
        let width = Double(size.width)
        let height = Double(size.height)

        // Design-doc drift, verbatim: blob i orbits cos(t·2π + i·0.71)·0.16 in x and
        // sin(phase·0.83)·0.12 in y, where `phase` is that same angle. `t` is *not* wrapped into
        // [0, 1) — x is 14 s periodic and y is 14/0.83 s periodic, so an unwrapped clock gives a
        // continuous quasi-periodic wander instead of a seam at every lap boundary.
        let phase = driftSeconds / InkMotion.backdropDrift * 2 * Double.pi + Double(index) * 0.71
        // The orbit is scaled by an envelope rather than switched on and off: cos(i·0.71) is not
        // zero at t = 0, so gating the formula directly would teleport every blob by up to 0.16
        // of the frame the instant `working` flipped. At amplitude 0 the blobs sit exactly on
        // their documented unit positions, which is what "stops entirely" should look like.
        let driftX = cos(phase) * Spec.driftAmplitudeX * amplitude * width
        let driftY = sin(phase * Spec.driftPhaseY) * Spec.driftAmplitudeY * amplitude * height

        // Unit positions are centre-relative: ±1 is the frame edge, so ±1.25 sits an eighth of
        // the frame outside it and only the falloff crosses back in.
        let x = width * 0.5 + Double(spec.x) * width * 0.5 + driftX
        let y = height * 0.5 + Double(spec.y) * height * 0.5 + driftY
            + (1 - rise) * Spec.riseDistance * height

        // "Radius 0.65 of the frame" — the larger dimension, so the falloff reads the same on a
        // 16:10 laptop panel and an ultrawide.
        let radius = max(width, height) * Spec.blobRadiusFraction

        return Circle()
            .fill(
                RadialGradient(
                    // `spec.color.opacity(0)` rather than `.clear`: fading to transparent *black*
                    // greys the falloff on the way out.
                    colors: [spec.color, spec.color.opacity(0)],
                    center: .center,
                    startRadius: 0,
                    endRadius: CGFloat(radius)
                )
            )
            .frame(width: CGFloat(radius * 2), height: CGFloat(radius * 2))
            .position(x: CGFloat(x), y: CGFloat(y))
    }

    /// Oval radial gradient, stops `[0, 0.54, 0.72, 1]`, alphas `[1 − clarity·0.82, 1, 1, 0]`.
    private func hollow(clarity: Double) -> some View {
        EllipticalGradient(
            stops: [
                .init(color: .white.opacity(1 - clarity * Spec.clarityDepth), location: 0),
                .init(color: .white, location: 0.54),
                .init(color: .white, location: 0.72),
                .init(color: .white.opacity(0), location: 1),
            ],
            center: .center,
            startRadiusFraction: 0,
            // Farthest-corner semantics (√2/2), matching the CSS `radial-gradient(ellipse …)`
            // this was lifted from. The default 0.5 would drive the mask to zero alpha at the
            // frame edges, which is exactly where the blobs live — it would erase the effect.
            endRadiusFraction: Spec.maskRadiusFraction
        )
    }
}

// MARK: - Spec

/// The shape of the field. Colour lives in `Ink.backdropBlobs` and every duration in `InkMotion`;
/// what is left here is geometry, which is this file's half of the design doc.
///
/// Free-standing because Swift forbids static stored properties inside a generic type.
private enum Spec {
    /// "Radius 0.65 of the frame."
    static let blobRadiusFraction = 0.65
    static let blurSigma: CGFloat = 24

    /// Down from 0.74 with the dark system: the blobs are low-alpha washes of `Ink.primary`, so
    /// this governs how much *shading* the sheet carries. Past ~0.6 the wash starts to read as dirt
    /// on the sheet rather than light across it.
    static let peakOpacity = 0.55
    static let riseDistance = 0.72

    static let driftAmplitudeX = 0.16
    static let driftAmplitudeY = 0.12
    static let driftPhaseY = 0.83
    /// How long the orbit takes to spin up or come to rest. Not a documented value — the doc
    /// fixes the orbit itself; see `blob(_:size:...)`.
    static let driftEnvelope = 0.9

    static let clarityDepth = 0.82
    static let maskRadiusFraction: CGFloat = 0.7071067811865476

    /// The longest ramp that can still be running after a state change is the 1800 ms rise.
    static let quiesceAfter = InkMotion.backdropRise + 0.2
}

// MARK: - Timing helpers

/// A value interpolating from `from` to `to`, read as a pure function of the clock. Retargeting
/// mid-flight picks up from wherever the value currently is, so a fast toggle never snaps.
private struct Ramp {
    private var from: Double
    private var to: Double
    private var start: Date
    private var duration: Double

    init(value: Double) {
        from = value
        to = value
        start = .distantPast
        duration = 0
    }

    func value(at now: Date) -> Double {
        guard duration > 0 else { return to }
        let progress = clamp01(now.timeIntervalSince(start) / duration)
        return from + (to - from) * easeOut(progress)
    }

    mutating func retarget(to newValue: Double, at now: Date, over newDuration: Double) {
        from = value(at: now)
        to = newValue
        start = now
        duration = newDuration
    }
}

private func clamp01(_ value: Double) -> Double {
    min(max(value, 0), 1)
}

/// Cubic ease-out — the standard motion-design curve, and within a frame of SwiftUI's
/// `.easeOut` bezier over the durations used here.
private func easeOut(_ t: Double) -> Double {
    1 - pow(1 - clamp01(t), 3)
}

/// Identity for "something about the motion changed, re-arm the quiescence timer".
private struct MotionKey: Equatable {
    let working: Bool
    let settled: Bool
}
