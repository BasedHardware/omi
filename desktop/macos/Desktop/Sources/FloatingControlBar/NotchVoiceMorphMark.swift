import OmiTheme
import SwiftUI

enum NotchVoiceMorphStage: Equatable {
  case ring
  case line
  case waveform
}

enum NotchVoiceMorphGeometry {
  static let lineBoundary: CGFloat = 0.55
  static let markSize = CGSize(width: 21, height: 21)
  static let dotCount = 8
  static let dotDiameterRatio: CGFloat = 0.18
  static let ringRadiusRatio: CGFloat = 0.33

  static func targetProgress(isListening: Bool) -> CGFloat {
    isListening ? 1 : 0
  }

  static func stage(progress rawProgress: CGFloat) -> NotchVoiceMorphStage {
    let progress = clamp(rawProgress)
    if progress <= 0.001 { return .ring }
    return progress < 0.999 ? .line : .waveform
  }

  static func lineProgress(_ rawProgress: CGFloat) -> CGFloat {
    smoothStep(clamp(clamp(rawProgress) / lineBoundary))
  }

  static func waveProgress(_ rawProgress: CGFloat, reduceMotion: Bool) -> CGFloat {
    guard !reduceMotion else { return 0 }
    let normalized = (clamp(rawProgress) - lineBoundary) / (1 - lineBoundary)
    return smoothStep(clamp(normalized))
  }

  /// Levels below this are treated as true silence. Ambient room noise
  /// measured on real hardware (after the capture service's own noise-floor
  /// subtraction) runs 0.005–0.013; the gate sits just above it so a quiet
  /// room renders a genuinely flat line / still ring, while even quiet
  /// speech (~0.03+) passes and is auto-gained to full range.
  static let displayLevelGate: CGFloat = 0.013

  /// Once speech has opened the gate, sub-gate levels keep rendering for this
  /// long, so the quieter tail of a phrase rides through instead of
  /// flatlining while the speaker is still talking.
  static let displayGateHangover: TimeInterval = 0.6

  /// During the hangover only genuine near-silence closes the wave; the
  /// capture pipeline's residual after noise-floor subtraction sits below
  /// this.
  static let displayLevelResidual: CGFloat = 0.006

  /// Perceptual knee applied after auto-gain normalization: lifts the quiet
  /// half of the range so word-to-word dynamics stay visible.
  static func displayKnee(_ normalized: CGFloat) -> CGFloat {
    normalized <= 0 ? 0 : pow(clamp(normalized), 0.65)
  }

  static func center(in size: CGSize) -> CGPoint {
    CGPoint(x: size.width / 2, y: size.height / 2)
  }

  static func dotPosition(
    index: Int,
    size: CGSize,
    progress rawProgress: CGFloat,
    waveOffset: CGFloat = 0
  ) -> CGPoint {
    let progress = clamp(rawProgress)
    let base = min(size.width, size.height)
    let center = center(in: size)
    let dotDiameter = base * dotDiameterRatio
    let ringRadius = base * ringRadiusRatio
    let angle = Double(index) / Double(dotCount) * Double.pi * 2 - Double.pi
    let ring = CGPoint(
      x: center.x + CGFloat(cos(angle)) * ringRadius,
      y: center.y + CGFloat(sin(angle)) * ringRadius
    )
    let lineStart = dotDiameter / 2
    let lineEnd = size.width - dotDiameter / 2
    let lineStep = (lineEnd - lineStart) / CGFloat(dotCount - 1)
    let line = CGPoint(
      x: lineStart + lineStep * CGFloat(index),
      y: center.y + waveOffset
    )
    let lineProgress = lineProgress(progress)
    return CGPoint(
      x: ring.x + (line.x - ring.x) * lineProgress,
      y: ring.y + (line.y - ring.y) * lineProgress
    )
  }

  // MARK: - Speaking (response playback) pulse

  /// Maximum outward radial displacement of a speaking-ring dot, as a
  /// fraction of the ring radius. Bounded so the outermost dot edge stays
  /// inside the 21pt identity slot: 6.93×1.24 + 3.78/2 ≈ 10.48 ≤ 10.5.
  static let speakingPushMax: CGFloat = 0.24

  /// Uniform outward expansion of the speaking ring: every dot pushes out
  /// together by the live output level, so the whole ring spikes on each
  /// sound peak and relaxes between them. All the motion comes from the
  /// fast attack/release on the level itself — no spatial wave, which in
  /// practice read as chewing or wobbling rather than a voice.
  static func speakingExpansion(level: CGFloat) -> CGFloat {
    clamp(level)
  }

  // MARK: - Listening waveform

  /// Center-weighted amplitude envelope so the live waveform reads like a
  /// level meter — strong in the middle, soft at the edges — instead of a
  /// uniform rope of dots.
  static func waveEnvelope(index: Int) -> CGFloat {
    let t = CGFloat(index) / CGFloat(dotCount - 1)
    return 0.45 + 0.55 * sin(.pi * t)
  }

  /// Vertical displacement for one waveform dot. Each dot bounces on its
  /// own blend of incommensurate frequencies — like adjacent frequency
  /// bands on an equalizer — so the line spikes up and down with the voice
  /// instead of rolling like a rope wave. Deterministic in (time, index)
  /// and normalized so |offset| ≤ amplitude.
  static func spikeOffset(time: TimeInterval, index: Int, amplitude: CGFloat) -> CGFloat {
    let seed = Double(index)
    let a = sin(time * (12.7 + seed * 1.9) + seed * 2.4)
    let b = sin(time * (19.3 - seed * 1.3) + seed * 5.1)
    let c = sin(time * (7.9 + seed * 0.7) + seed * 1.7) * 0.6
    return CGFloat((a + b + c) / 2.6) * amplitude * waveEnvelope(index: index)
  }

  private static func smoothStep(_ value: CGFloat) -> CGFloat {
    value * value * (3 - 2 * value)
  }

  private static func clamp(_ value: CGFloat) -> CGFloat {
    min(max(value, 0), 1)
  }
}

/// Turns raw audio levels into full-range display levels at frame rate:
/// gate (true silence stays zero) → auto-gain (normalize against a slowly
/// decaying running peak, so normal speech uses the whole visual range no
/// matter the absolute mic/output scale) → perceptual knee → attack/release
/// smoothing. A class so a Canvas draw pass can advance it per frame.
final class VoiceLevelDisplay {
  private let smoother: VoiceLevelSmoother
  /// Reference peak never falls below this, so noise between the gate and
  /// `minPeak` cannot be amplified to full scale.
  private let minPeak: CGFloat
  /// Per-second multiplicative decay of the running peak; slow enough that
  /// one loud word doesn't crush the next quiet one to invisibility.
  private let peakHalfLife: TimeInterval
  private var peak: CGFloat
  private var lastTime: TimeInterval?
  /// Last moment the raw level cleared the opening gate; sub-gate levels
  /// within `displayGateHangover` of it still render, so the quiet tail of a
  /// phrase doesn't flatline mid-word.
  private var lastVoicedTime: TimeInterval?

  init(
    minPeak: CGFloat,
    peakHalfLife: TimeInterval = 4,
    attackTau: TimeInterval = 0.05,
    releaseTau: TimeInterval = 0.22
  ) {
    self.minPeak = minPeak
    self.peakHalfLife = peakHalfLife
    peak = minPeak
    smoother = VoiceLevelSmoother(attackTau: attackTau, releaseTau: releaseTau)
  }

  func step(rawLevel: CGFloat, at time: TimeInterval) -> CGFloat {
    if rawLevel > NotchVoiceMorphGeometry.displayLevelGate {
      lastVoicedTime = time
    }
    let inHangover =
      lastVoicedTime.map {
        time - $0 <= NotchVoiceMorphGeometry.displayGateHangover
      } ?? false
    let passes =
      rawLevel > NotchVoiceMorphGeometry.displayLevelGate
      || (inHangover && rawLevel > NotchVoiceMorphGeometry.displayLevelResidual)
    let gated = passes ? min(rawLevel, 1) : 0
    if let last = lastTime, time > last {
      let dt = min(time - last, 1)
      peak = max(minPeak, peak * pow(0.5, CGFloat(dt / peakHalfLife)))
    }
    lastTime = time
    peak = max(peak, gated)
    let normalized = gated == 0 ? 0 : NotchVoiceMorphGeometry.displayKnee(gated / peak)
    return smoother.step(target: normalized, at: time)
  }
}

/// Frame-rate exponential smoother with asymmetric attack/release, so the
/// waveform and speaking pulse jump quickly on onset but fall away gently.
/// A class so a Canvas draw pass can advance it without SwiftUI state churn.
final class VoiceLevelSmoother {
  private(set) var displayed: CGFloat
  private var lastTime: TimeInterval?
  private let attackTau: TimeInterval
  private let releaseTau: TimeInterval

  init(initial: CGFloat = 0, attackTau: TimeInterval = 0.05, releaseTau: TimeInterval = 0.22) {
    displayed = initial
    self.attackTau = attackTau
    self.releaseTau = releaseTau
  }

  @discardableResult
  func step(target rawTarget: CGFloat, at time: TimeInterval) -> CGFloat {
    let target = min(max(rawTarget, 0), 1)
    guard let last = lastTime, time > last else {
      lastTime = time
      displayed = target
      return displayed
    }
    // Cap dt so a paused TimelineView resuming doesn't teleport the level.
    let dt = min(time - last, 0.25)
    lastTime = time
    let tau = target > displayed ? attackTau : releaseTau
    let alpha = 1 - exp(-dt / tau)
    displayed += (target - displayed) * alpha
    return displayed
  }
}

struct NotchVoiceMorphMark: View {
  let dotColors: [Color]
  let isListening: Bool
  let isThinking: Bool
  var isSpeaking: Bool = false

  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @State private var morphProgress: CGFloat = 0
  /// Reference peaks measured on real hardware: close-mic speech ~0.03–0.2
  /// RMS after the capture noise floor; post-mixer reply speech ~0.1–0.25.
  /// The mic side attacks tight so the wave snaps to syllables, but its peak
  /// half-life is short so a loud opening word doesn't crush the quieter
  /// tail of the phrase, and release rides through inter-syllable dips. The
  /// voice side is tuned fast both ways: the uniform ring expansion IS the
  /// level, so it must spike and relax per sound peak, not glide.
  @State private var micLevelDisplay = VoiceLevelDisplay(
    minPeak: 0.035, peakHalfLife: 2, attackTau: 0.02, releaseTau: 0.16)
  @State private var voiceLevelDisplay = VoiceLevelDisplay(
    minPeak: 0.1, attackTau: 0.012, releaseTau: 0.09)

  var body: some View {
    TimelineView(.animation(paused: !isListening && !isThinking && !isSpeaking)) { timeline in
      Canvas { context, size in
        draw(into: &context, size: size, date: timeline.date)
      }
    }
    .onAppear {
      setMorphProgress(NotchVoiceMorphGeometry.targetProgress(isListening: isListening))
    }
    .onChange(of: isListening) { _, listening in
      setMorphProgress(NotchVoiceMorphGeometry.targetProgress(isListening: listening))
    }
    .accessibilityElement(children: .ignore)
    .accessibilityLabel(
      isListening ? "Listening" : isSpeaking ? "Speaking" : isThinking ? "Thinking" : "Omi")
  }

  private func setMorphProgress(_ progress: CGFloat) {
    var transaction = Transaction()
    transaction.animation = reduceMotion ? nil : .easeInOut(duration: 0.34)
    withTransaction(transaction) {
      morphProgress = progress
    }
  }

  private func draw(into context: inout GraphicsContext, size: CGSize, date: Date) {
    let base = min(size.width, size.height)
    let center = NotchVoiceMorphGeometry.center(in: size)
    let dotDiameter = base * NotchVoiceMorphGeometry.dotDiameterRatio
    let waveProgress = NotchVoiceMorphGeometry.waveProgress(
      morphProgress,
      reduceMotion: reduceMotion
    )
    let time = date.timeIntervalSinceReferenceDate
    // Live (un-throttled) mic level through gate → auto-gain → knee →
    // smoothing. Silence maps to exactly zero amplitude — the listening line
    // goes flat between words — while normal speech spans the full wave
    // height regardless of the absolute mic scale.
    let level = micLevelDisplay.step(
      rawLevel: CGFloat(AudioLevelMonitor.shared.liveMicrophoneLevel), at: time)
    let amplitude = base * 0.32 * waveProgress * level
    let thinkingRotation =
      isThinking && !reduceMotion && morphProgress < 0.001
      ? time * 2 * .pi / 0.9
      : 0
    // Response playback expands the whole ring uniformly by the assistant's
    // live output level (mixer tap): every sound peak spikes the ring
    // outward and it snaps back between peaks. Pauses in the reply leave a
    // clean still ring. Dot size stays constant — the voice displaces the
    // ring, it doesn't inflate it. Listening owns the waveform, so this
    // applies only in ring formation.
    let speakingPresentation = isSpeaking && !isListening && morphProgress < 0.001
    let speakingLevel =
      speakingPresentation && !reduceMotion
      ? voiceLevelDisplay.step(
        rawLevel: CGFloat(AudioLevelMonitor.shared.liveVoicePlaybackLevel), at: time)
      : 0

    for index in 0..<NotchVoiceMorphGeometry.dotCount {
      let progress =
        thinkingRotation == 0
        ? morphProgress
        : 0
      var position = NotchVoiceMorphGeometry.dotPosition(
        index: index,
        size: size,
        progress: progress,
        waveOffset: NotchVoiceMorphGeometry.spikeOffset(
          time: time, index: index, amplitude: amplitude)
      )
      if thinkingRotation != 0 || speakingPresentation {
        let angle =
          Double(index) / Double(NotchVoiceMorphGeometry.dotCount) * Double.pi * 2
          - Double.pi + thinkingRotation
        let push = NotchVoiceMorphGeometry.speakingExpansion(level: speakingLevel)
        let ringRadius =
          base * NotchVoiceMorphGeometry.ringRadiusRatio
          * (1 + NotchVoiceMorphGeometry.speakingPushMax * push)
        position = CGPoint(
          x: center.x + CGFloat(cos(angle)) * ringRadius,
          y: center.y + CGFloat(sin(angle)) * ringRadius
        )
      }
      // PTT capture is one Omi-owned state, not an agent-status legend. White
      // keeps every waveform dot legible against the notch's black chrome.
      // Color follows the presentation, not the pulse magnitude, so a pause
      // in the reply can't flicker the ring between white and status colors.
      let color =
        isListening || speakingPresentation
        ? Color.white.opacity(0.98)
        : dotColors.indices.contains(index)
          ? dotColors[index]
          : Color.white.opacity(0.96)
      let rect = CGRect(
        x: position.x - dotDiameter / 2,
        y: position.y - dotDiameter / 2,
        width: dotDiameter,
        height: dotDiameter
      )
      context.fill(Path(ellipseIn: rect), with: .color(color))
    }
  }
}
