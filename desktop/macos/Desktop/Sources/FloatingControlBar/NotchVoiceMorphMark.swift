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

  // MARK: - Dictation tint

  /// How long the dots take to ease from white to red once a hold is
  /// recognised as a dictation. Long enough to read as a deliberate change,
  /// short enough to land before the next word.
  static let dictationTintDuration: TimeInterval = 0.28

  /// Red the dots settle on. Warm and bright so it holds up against the
  /// notch's black glass at a 3.8pt dot.
  static let dictationTint: (red: CGFloat, green: CGFloat, blue: CGFloat) = (1.0, 0.30, 0.26)

  /// Ease-in blend (0 = white, 1 = red) `elapsed` seconds after the
  /// dictation was recognised. Nil elapsed means not dictating.
  static func dictationBlend(elapsed: TimeInterval?, reduceMotion: Bool) -> CGFloat {
    guard let elapsed else { return 0 }
    if reduceMotion { return 1 }
    let t = clamp(CGFloat(elapsed / dictationTintDuration))
    return t * t
  }

  /// How long the red takes to fade back once the dictation ends — the key
  /// came up, the turn closed. Slower than the ease-in: the arrival is a
  /// signal worth noticing, the departure is not.
  static let dictationTintFadeDuration: TimeInterval = 0.55

  /// Ease-out blend `elapsed` seconds after the dictation ended, starting
  /// from `peak` — wherever the ease-in had got to, so a release during the
  /// ease-in fades from that partial red rather than jumping to full red
  /// first. Smooth in and out of the fade, never below zero.
  static func dictationFadeBlend(elapsed: TimeInterval, from peak: CGFloat, reduceMotion: Bool) -> CGFloat {
    if reduceMotion { return 0 }
    let t = clamp(CGFloat(elapsed / dictationTintFadeDuration))
    return clamp(peak) * (1 - smoothStep(t))
  }

  /// The dot colour for a blend: `base` — the colour the dot would otherwise
  /// be — with the tint mixed in. While dictating the base is the listening
  /// white; during the fade it is whatever the dot is returning to, so the
  /// red eases straight into a status colour rather than through white.
  static func dictationDotColor(
    blend rawBlend: CGFloat, base: (red: CGFloat, green: CGFloat, blue: CGFloat) = (1, 1, 1)
  ) -> Color {
    let blend = clamp(rawBlend)
    return Color(
      red: base.red + (dictationTint.red - base.red) * blend,
      green: base.green + (dictationTint.green - base.green) * blend,
      blue: base.blue + (dictationTint.blue - base.blue) * blend
    ).opacity(0.98)
  }

  /// sRGB components of a dot colour, for mixing. White when the colour
  /// cannot be resolved (a dynamic system colour off the main thread).
  static func components(of color: Color) -> (red: CGFloat, green: CGFloat, blue: CGFloat) {
    guard let resolved = NSColor(color).usingColorSpace(.sRGB) else { return (1, 1, 1) }
    return (resolved.redComponent, resolved.greenComponent, resolved.blueComponent)
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

/// Where the dictation tint is in its life: easing in from the moment the
/// wake word was heard, easing out from the moment the dictation ended.
/// Pure, so the transitions and the blend can be tested against a clock.
struct NotchDictationTint: Equatable {
  enum Phase: Equatable {
    case off
    case easingIn(since: Date)
    /// Fading from `peak`, the blend at the instant the dictation ended.
    case easingOut(since: Date, peak: CGFloat)
  }

  private(set) var phase: Phase = .off

  /// Whether the dots still need frames: the timeline must not pause on the
  /// last red frame while a fade is under way.
  var isAnimating: Bool {
    if case .off = phase { return false }
    return true
  }

  /// Applies the presentation's dictating flag at `now`. Turning off begins a
  /// fade from wherever the ease-in had got to; turning on again mid-fade
  /// restarts the ease-in from that same partial red rather than from white.
  mutating func update(isDictating: Bool, at now: Date, reduceMotion: Bool) {
    switch (phase, isDictating) {
    case (.off, true):
      phase = .easingIn(since: now)
    case (.easingOut(_, _), true):
      let current = blend(at: now, reduceMotion: reduceMotion)
      // Rewind the start so the ease-in resumes at `current`.
      let resumed = NotchVoiceMorphGeometry.dictationTintDuration * Double(sqrt(current))
      phase = .easingIn(since: now.addingTimeInterval(-resumed))
    case (.easingIn(_), false):
      let peak = blend(at: now, reduceMotion: reduceMotion)
      phase = peak > 0 ? .easingOut(since: now, peak: peak) : .off
    case (.easingIn, true), (.easingOut, false), (.off, false):
      break
    }
  }

  /// A fade that has run its course is over; called from the timeline so the
  /// animation can pause once the dots are back to their resting colour.
  mutating func settleIfFaded(at now: Date, reduceMotion: Bool) {
    guard case .easingOut = phase else { return }
    // Below what a 3.8pt dot can show; also sidesteps the last float ulp of
    // an elapsed-versus-duration comparison.
    if blend(at: now, reduceMotion: reduceMotion) < 0.005 {
      phase = .off
    }
  }

  /// 0 = the dot's own colour, 1 = full red.
  func blend(at now: Date, reduceMotion: Bool) -> CGFloat {
    switch phase {
    case .off:
      return 0
    case .easingIn(let since):
      return NotchVoiceMorphGeometry.dictationBlend(elapsed: now.timeIntervalSince(since), reduceMotion: reduceMotion)
    case .easingOut(let since, let peak):
      return NotchVoiceMorphGeometry.dictationFadeBlend(
        elapsed: now.timeIntervalSince(since), from: peak, reduceMotion: reduceMotion)
    }
  }
}

struct NotchVoiceMorphMark: View {
  let dotColors: [Color]
  let isListening: Bool
  let isThinking: Bool
  var isSpeaking: Bool = false
  /// The hold has been recognised as a dictation: the dots ease to red and
  /// keep whatever motion the presentation already has. When it ends they
  /// ease back out rather than snapping.
  var isDictating: Bool = false

  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @State private var morphProgress: CGFloat = 0
  @State private var dictationTint = NotchDictationTint()
  /// Ends the fade-out's claim on the timeline once it has run its course.
  @State private var dictationFadeSettle: Task<Void, Never>?
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
    TimelineView(
      .animation(paused: !isListening && !isThinking && !isSpeaking && !isDictating && !dictationTint.isAnimating)
    ) { timeline in
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
    .onChange(of: isDictating, initial: true) { _, dictating in
      let now = Date()
      dictationTint.update(isDictating: dictating, at: now, reduceMotion: reduceMotion)
      dictationFadeSettle?.cancel()
      dictationFadeSettle = nil
      guard case .easingOut = dictationTint.phase else { return }
      // The fade keeps the timeline running; once it is done, let it pause.
      dictationFadeSettle = Task { @MainActor in
        let fade = reduceMotion ? 0 : NotchVoiceMorphGeometry.dictationTintFadeDuration
        try? await Task.sleep(nanoseconds: UInt64(fade * 1_000_000_000))
        guard !Task.isCancelled else { return }
        dictationTint.settleIfFaded(at: Date(), reduceMotion: reduceMotion)
      }
    }
    .accessibilityElement(children: .ignore)
    .accessibilityLabel(
      isDictating ? "Dictating" : isListening ? "Listening" : isSpeaking ? "Speaking" : isThinking ? "Thinking" : "Omi")
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
      // A dictation tints every dot red, eased in from the moment the wake
      // word was heard, on top of whatever motion the presentation has:
      // the waveform keeps spiking while listening, the ring keeps turning
      // while the paste is prepared. Only the colour changes. When the
      // dictation ends the red eases back out into whatever the dot is
      // returning to — the white of a still-listening bar, or an agent's
      // status colour — instead of snapping.
      let restingColor: Color =
        isListening || speakingPresentation
        ? NotchGlass.primary.opacity(0.98)
        : dotColors.indices.contains(index)
          ? dotColors[index]
          : NotchGlass.primary.opacity(0.96)
      let dictationBlend = dictationTint.blend(at: date, reduceMotion: reduceMotion)
      // Branch on the state, not the blend: the first dictation frame has a
      // zero blend, and it must start from white, never from a status colour.
      let color: Color
      if isDictating {
        color = NotchVoiceMorphGeometry.dictationDotColor(blend: dictationBlend)
      } else if dictationBlend > 0 {
        color = NotchVoiceMorphGeometry.dictationDotColor(
          blend: dictationBlend, base: NotchVoiceMorphGeometry.components(of: restingColor))
      } else {
        color = restingColor
      }
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
