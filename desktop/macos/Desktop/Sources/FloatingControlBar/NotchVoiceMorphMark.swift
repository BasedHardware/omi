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
  /// Even a quiet room needs to read as a live capture rather than eight
  /// apparently static dots. This is display gain only; it never affects VAD.
  static let quietLevelFloor: CGFloat = 0.28

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

  static func normalizedLevel(_ microphoneLevel: CGFloat) -> CGFloat {
    min(max(microphoneLevel * 2.4, quietLevelFloor), 1)
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

  private static func smoothStep(_ value: CGFloat) -> CGFloat {
    value * value * (3 - 2 * value)
  }

  private static func clamp(_ value: CGFloat) -> CGFloat {
    min(max(value, 0), 1)
  }
}

struct NotchVoiceMorphMark: View {
  let dotColors: [Color]
  let isListening: Bool
  let isThinking: Bool

  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @State private var morphProgress: CGFloat = 0

  var body: some View {
    TimelineView(.animation(paused: !isListening && !isThinking)) { timeline in
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
    .accessibilityLabel(isListening ? "Listening" : isThinking ? "Thinking" : "Omi")
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
    let level = CGFloat(AudioLevelMonitor.shared.microphoneLevel)
    let amplitude =
      base * 0.28 * waveProgress
      * NotchVoiceMorphGeometry.normalizedLevel(level)
    let time = date.timeIntervalSinceReferenceDate
    let thinkingRotation =
      isThinking && !reduceMotion && morphProgress < 0.001
      ? time * 2 * .pi / 0.9
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
        waveOffset: CGFloat(sin(time * 9 - Double(index) * 0.82)) * amplitude
      )
      if thinkingRotation != 0 {
        let angle =
          Double(index) / Double(NotchVoiceMorphGeometry.dotCount) * Double.pi * 2
          - Double.pi + thinkingRotation
        let ringRadius = base * NotchVoiceMorphGeometry.ringRadiusRatio
        position = CGPoint(
          x: center.x + CGFloat(cos(angle)) * ringRadius,
          y: center.y + CGFloat(sin(angle)) * ringRadius
        )
      }
      // PTT capture is one Omi-owned state, not an agent-status legend. White
      // keeps every waveform dot legible against the notch's black chrome.
      let color =
        isListening
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
