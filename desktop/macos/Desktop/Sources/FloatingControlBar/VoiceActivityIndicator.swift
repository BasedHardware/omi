import SwiftUI

/// The floating bar's single status element. One coherent shape that changes its
/// motion law, color, and energy per state — never a hard icon swap — so the user
/// always knows, at a glance and without labels, whether the assistant is:
///
///   • idle      — a calm, barely-breathing sliver (nearly still, muted)
///   • listening — a red waveform reacting to "you" (red is reserved for recording)
///   • thinking  — a cool blue→violet gradient sweeping on its own fixed clock; the
///                 self-driven motion (no audio) reads as "working, wait" — critical
///                 so a late reply never looks like "done / idle"
///   • speaking  — a green waveform driven by the model's actual output amplitude
///                 ("it's talking", clearly distinct from the red "you" waveform)
///
/// Performance: idle (the long-lived resting state) uses a single Core Animation
/// property animation — no per-frame redraw. The active states use one
/// `TimelineView(.animation)` + `Canvas` (a single GPU-friendly draw pass, no
/// view-graph diffing per frame), and only run for the few seconds a turn is live.
/// No blur/shadow/material (those force offscreen passes) — glow is faked with
/// translucent gradient fills.
struct VoiceActivityIndicator: View {
    let activity: VoiceActivity
    /// Smoothed 0…1 amplitude of the model's spoken reply (drives the speaking waveform).
    var level: CGFloat = 0

    var body: some View {
        ZStack {
            switch activity {
            case .idle:
                IdleBreath()
            case .listening:
                WaveformBars(palette: .listening, level: 0, reactive: false)
            case .thinking:
                ThinkingSweep()
            case .speaking:
                WaveformBars(palette: .speaking, level: level, reactive: true)
            }
        }
        // Cross-fade + gentle scale between states so energy "ramps" rather than snaps.
        .transition(.opacity.combined(with: .scale(scale: 0.7)))
        .animation(.spring(response: 0.4, dampingFraction: 0.86), value: activity)
    }
}

// MARK: - Idle

/// A short muted capsule that breathes very slowly. Intentionally low-energy so the
/// resting bar never pulls the eye. Pure Core Animation — no redraw loop.
private struct IdleBreath: View {
    @State private var breathing = false

    var body: some View {
        Capsule()
            .fill(Color.white.opacity(breathing ? 0.55 : 0.26))
            .frame(width: 26, height: 5)
            .scaleEffect(x: 1, y: breathing ? 1.0 : 0.7, anchor: .center)
            .onAppear {
                withAnimation(.easeInOut(duration: 2.8).repeatForever(autoreverses: true)) {
                    breathing = true
                }
            }
    }
}

// MARK: - Thinking

/// A cool blue→violet gradient that pans continuously across a capsule at a fixed,
/// self-driven rate. The autonomous (non-audio) motion is the cue that the model is
/// working — so a slow reply reads as "wait", never as "done".
private struct ThinkingSweep: View {
    // Hoisted: the colors are state-constant, so only the gradient positions change
    // per frame — no point rebuilding these Gradient values 60–120×/s.
    private static let sweepGradient = Gradient(colors: [
        Color(red: 0.70, green: 0.49, blue: 1.0),  // violet
        Color(red: 0.43, green: 0.55, blue: 1.0),  // blue
        Color(red: 0.70, green: 0.49, blue: 1.0),
        Color(red: 0.43, green: 0.55, blue: 1.0),
        Color(red: 0.70, green: 0.49, blue: 1.0),
    ])
    private static let glowGradient = Gradient(colors: [
        Color.white.opacity(0.45), Color.white.opacity(0),
    ])

    var body: some View {
        TimelineView(.animation) { timeline in
            Canvas { context, size in
                let t = timeline.date.timeIntervalSinceReferenceDate
                let rect = CGRect(origin: .zero, size: size)
                let capsule = Capsule().path(in: rect)

                // Dim base track so the capsule reads even at the low point of the sweep.
                context.fill(capsule, with: .color(.white.opacity(0.10)))

                context.drawLayer { layer in
                    layer.clip(to: capsule)

                    // Pan a symmetric violet→blue→violet gradient horizontally. Symmetric
                    // stops + a span twice the width mean the loop has no visible seam.
                    let period = 2.2  // seconds per full pan
                    let phase = (t.truncatingRemainder(dividingBy: period)) / period
                    let span = size.width * 2
                    let shift = CGFloat(phase) * span
                    layer.fill(
                        Rectangle().path(in: rect),
                        with: .linearGradient(
                            Self.sweepGradient,
                            startPoint: CGPoint(x: -span + shift, y: 0),
                            endPoint: CGPoint(x: shift, y: 0)))

                    // Soft moving highlight (faked glow) gliding with an eased ping-pong
                    // so it slows at the ends instead of snapping back.
                    let eased = 0.5 - 0.5 * cos(phase * 2 * .pi)
                    let cx = size.width * CGFloat(eased)
                    let glowR = max(size.height, size.width * 0.32)
                    layer.fill(
                        Rectangle().path(in: rect),
                        with: .radialGradient(
                            Self.glowGradient,
                            center: CGPoint(x: cx, y: size.height / 2),
                            startRadius: 0, endRadius: glowR))
                }
            }
        }
        .frame(width: 34, height: 8)
    }
}

// MARK: - Waveform (listening + speaking)

/// Color treatment for a waveform state — a precomputed top→bottom gradient (constant
/// per state, so it's built once here, not per-bar per-frame inside the Canvas).
private struct WaveformPalette {
    let gradient: Gradient

    /// Red — reserved exclusively for recording the user ("you").
    static let listening = WaveformPalette(gradient: Gradient(colors: [
        Color(red: 1.0, green: 0.42, blue: 0.42),
        Color(red: 1.0, green: 0.18, blue: 0.33),
    ]))

    /// Green/mint — the assistant speaking ("it"); clearly not the red "you" or blue "thinking".
    static let speaking = WaveformPalette(gradient: Gradient(colors: [
        Color(red: 0.46, green: 0.93, blue: 0.74),
        Color(red: 0.20, green: 0.83, blue: 0.60),
    ]))
}

/// A small centered equalizer. `reactive` bars track the live `level` (speaking);
/// non-reactive bars animate on a lively synthetic clock (listening). A per-bar phase
/// + center weighting gives an organic "voice blob" rather than a marching pattern.
private struct WaveformBars: View {
    let palette: WaveformPalette
    var level: CGFloat
    var reactive: Bool

    private let barCount = 5

    var body: some View {
        TimelineView(.animation) { timeline in
            Canvas { context, size in
                let t = timeline.date.timeIntervalSinceReferenceDate
                // Equal bars and gaps: n bars, n-1 gaps, all one unit wide.
                let unit = size.width / CGFloat(barCount * 2 - 1)
                let radius = unit / 2
                let minH = size.height * 0.28

                for i in 0..<barCount {
                    // Center bars are weighted taller so it reads as a rounded voice shape.
                    let distFromCenter = abs(CGFloat(i) - CGFloat(barCount - 1) / 2)
                    let centerWeight = 1.0 - distFromCenter / CGFloat(barCount)

                    let wobble = (sin(t * 7.5 + Double(i) * 1.1) + 1) / 2  // 0…1
                    let drive: CGFloat
                    if reactive {
                        // Audio-reactive: height follows the smoothed amplitude, with a
                        // little per-bar wobble so quiet passages still feel alive.
                        drive = min(1, level * (0.55 + 0.9 * centerWeight) + CGFloat(wobble) * 0.18)
                    } else {
                        // Listening: purely synthetic but lively equalizer motion.
                        drive = CGFloat(wobble) * (0.45 + 0.55 * centerWeight)
                    }

                    let h = max(minH, minH + (size.height - minH) * drive)
                    let x = CGFloat(i) * unit * 2
                    let y = (size.height - h) / 2
                    let barRect = CGRect(x: x, y: y, width: unit, height: h)
                    let bar = Capsule().path(in: barRect)
                    context.fill(
                        bar,
                        with: .linearGradient(
                            palette.gradient,
                            startPoint: CGPoint(x: x, y: y),
                            endPoint: CGPoint(x: x, y: y + h)))
                }
            }
        }
        .frame(width: 34, height: 16)
    }
}
