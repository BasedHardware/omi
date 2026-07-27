import OmiTheme
import SwiftUI

enum NotchVoiceMorphStage: Equatable {
  case ring
  case line
  case waveform
}

enum NotchVoiceMorphGeometry {
  static let lineBoundary: CGFloat = 0.55

  static func targetProgress(isListening: Bool) -> CGFloat {
    isListening ? 1 : 0
  }

  static func stage(progress rawProgress: CGFloat) -> NotchVoiceMorphStage {
    let progress = clamp(rawProgress)
    if progress <= 0.001 { return .ring }
    return progress < 0.999 ? .line : .waveform
  }

  static func lineProgress(_ rawProgress: CGFloat) -> CGFloat {
    smoothStep(clamp(rawProgress) / lineBoundary)
  }

  static func waveProgress(_ rawProgress: CGFloat, reduceMotion: Bool) -> CGFloat {
    guard !reduceMotion else { return 0 }
    let normalized = (clamp(rawProgress) - lineBoundary) / (1 - lineBoundary)
    return smoothStep(clamp(normalized))
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

  private static let dotCount = 8
  private static let dotDiameterRatio: CGFloat = 0.18
  private static let ringRadiusRatio: CGFloat = 0.33

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
    // Keep the resting ring at the exact trailing-aligned position used by the
    // existing 21pt Omi mark while allowing the waveform to grow leftward.
    let center = CGPoint(x: size.width - base / 2, y: size.height / 2)
    let dotDiameter = base * Self.dotDiameterRatio
    let ringRadius = base * Self.ringRadiusRatio
    let lineStart = dotDiameter / 2
    let lineEnd = size.width - dotDiameter / 2
    let lineStep = (lineEnd - lineStart) / CGFloat(Self.dotCount - 1)
    let lineProgress = NotchVoiceMorphGeometry.lineProgress(morphProgress)
    let waveProgress = NotchVoiceMorphGeometry.waveProgress(
      morphProgress,
      reduceMotion: reduceMotion
    )
    let level = CGFloat(AudioLevelMonitor.shared.microphoneLevel)
    let amplitude = base * 0.28 * waveProgress * min(max(level * 2.4, 0.12), 1)
    let time = date.timeIntervalSinceReferenceDate
    let thinkingRotation =
      isThinking && !reduceMotion && morphProgress < 0.001
      ? time * 2 * .pi / 0.9
      : 0

    for index in 0..<Self.dotCount {
      let angle =
        Double(index) / Double(Self.dotCount) * Double.pi * 2
        - Double.pi + thinkingRotation
      let ring = CGPoint(
        x: center.x + CGFloat(cos(angle)) * ringRadius,
        y: center.y + CGFloat(sin(angle)) * ringRadius
      )
      let lineX = lineStart + lineStep * CGFloat(index)
      let waveY =
        center.y
        + CGFloat(sin(time * 9 - Double(index) * 0.82)) * amplitude
      let position = CGPoint(
        x: ring.x + (lineX - ring.x) * lineProgress,
        y: ring.y + (waveY - ring.y) * lineProgress
      )
      let color =
        dotColors.indices.contains(index)
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
