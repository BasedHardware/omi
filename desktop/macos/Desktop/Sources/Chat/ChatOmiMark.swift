import SwiftUI

private let chatMarkRestingOpacity = 0.95

enum ChatMarkMotion: Equatable {
  case gather
  case wave

  var cycle: Double {
    switch self {
    case .gather: return 1.6
    case .wave: return 2.4
    }
  }

  var spin: Double {
    switch self {
    case .gather: return 1.2
    case .wave: return 0.6
    }
  }

  static func forTool(_ toolName: String) -> ChatMarkMotion {
    let cleaned =
      toolName.hasPrefix("mcp__")
      ? String(toolName.split(separator: "__").last ?? Substring(toolName))
      : toolName
    let lower = cleaned.lowercased()
    let head =
      lower.split(separator: ":").first.map(String.init)?
      .trimmingCharacters(in: .whitespaces) ?? lower

    let acting: Set<String> = [
      "write", "edit", "multiedit", "notebookedit", "bash",
      "spawn_agent", "run_agent_and_wait", "send_agent_message", "run_attempt",
    ]
    return acting.contains(head) ? .wave : .gather
  }
}

struct ChatOmiMark: View {
  enum Anchor {
    case leading
    case centered
  }

  var motion: ChatMarkMotion?
  var size: CGFloat = 30
  var anchor: Anchor = .leading

  @State private var model = ChatMarkModel()
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  private var isWorking: Bool { motion != nil }

  var body: some View {
    TimelineView(
      .animation(minimumInterval: isWorking ? nil : 1.0 / 20.0, paused: reduceMotion)
    ) { timeline in
      Canvas { context, canvasSize in
        model.advance(
          to: timeline.date,
          motion: motion,
          reduceMotion: reduceMotion
        )
        model.draw(into: &context, size: canvasSize, base: size, anchor: anchor)
      }
    }
    .frame(width: size * ChatMarkModel.widthRatio, height: size)
    .padding(.leading, anchor == .leading ? -size * ChatMarkModel.leftAnchor : 0)
    .accessibilityHidden(true)
  }
}

struct ChatMarkModelSnapshot: Equatable {
  let intensity: Double
  let phase: Double
  let motion: ChatMarkMotion
}

@MainActor
final class ChatMarkModel {
  private static let count = 8
  private static let dotDiameterRatio: CGFloat = 0.18
  private static let ringRadiusRatio: CGFloat = 0.33
  private static let startAngle = -Double.pi
  private static let restingSpin: Double = 2 * .pi / 18

  static let widthRatio: CGFloat = 1.7
  static let centerX: CGFloat = 0.55
  static let leftAnchor: CGFloat = 0.13

  private var rotation: Double = 0
  private var intensity: Double = 0
  private var phase: Double = 0
  private var motion: ChatMarkMotion = .gather
  private var pendingMotion: ChatMarkMotion?
  private var wasWorking = false
  private var lastTime: CFTimeInterval?

  var snapshot: ChatMarkModelSnapshot {
    ChatMarkModelSnapshot(intensity: intensity, phase: phase, motion: motion)
  }

  func advance(to date: Date, motion requested: ChatMarkMotion?, reduceMotion: Bool) {
    let now = date.timeIntervalSinceReferenceDate
    let dt = lastTime.map { min(0.05, max(0, now - $0)) } ?? (1.0 / 60.0)
    lastTime = now

    let working = requested != nil && !reduceMotion

    if let requested {
      if !wasWorking {
        motion = requested
        pendingMotion = nil
        phase = 0
      } else if requested != motion {
        pendingMotion = requested
      } else {
        pendingMotion = nil
      }
    }
    wasWorking = working

    intensity += ((working ? 1 : 0) - intensity) * min(1, dt * 3.2)
    rotation += dt * (Self.restingSpin + motion.spin * intensity)

    guard intensity > 0.001 else {
      phase = 0
      return
    }
    phase += dt / motion.cycle
    if phase >= 1 {
      phase -= 1
      if let pendingMotion {
        motion = pendingMotion
        self.pendingMotion = nil
      }
    }
  }

  func draw(
    into context: inout GraphicsContext,
    size: CGSize,
    base: CGFloat,
    anchor: ChatOmiMark.Anchor
  ) {
    let dotDiameter = base * Self.dotDiameterRatio
    let ringRadius = base * Self.ringRadiusRatio
    let centerY = size.height / 2
    let centerX = anchor == .leading ? base * Self.centerX : size.width / 2
    let lineStart =
      anchor == .leading
      ? base * Self.leftAnchor + dotDiameter / 2
      : dotDiameter / 2
    let lineEnd = size.width - dotDiameter / 2
    let lineStep = (lineEnd - lineStart) / CGFloat(Self.count - 1)

    for index in 0..<Self.count {
      let frame = frame(dot: index)
      let angle =
        2 * Double.pi * Double(index) / Double(Self.count)
        + Self.startAngle + rotation
      let ringX = centerX + ringRadius * CGFloat(frame.radiusX) * CGFloat(cos(angle))
      let ringY = centerY + ringRadius * CGFloat(frame.radiusY) * CGFloat(sin(angle))
      let lineX = lineStart + lineStep * CGFloat(index)

      let x = ringX + (lineX - ringX) * CGFloat(frame.line)
      let y =
        ringY + (centerY - ringY) * CGFloat(frame.line)
        + base * CGFloat(frame.offsetY)

      let diameter = dotDiameter * CGFloat(frame.scale)
      let rect = CGRect(
        x: x - diameter / 2,
        y: y - diameter / 2,
        width: diameter,
        height: diameter
      )
      context.fill(Path(ellipseIn: rect), with: .color(.white.opacity(frame.opacity)))
    }
  }

  private struct DotFrame {
    var radiusX: Double = 1
    var radiusY: Double = 1
    var scale: Double = 1
    var opacity: Double = chatMarkRestingOpacity
    var line: Double = 0
    var offsetY: Double = 0
  }

  private func frame(dot index: Int) -> DotFrame {
    guard intensity > 0.001 else { return DotFrame() }
    let working = motion == .gather ? gather(dot: index) : wave(dot: index)
    let transition = intensity
    return DotFrame(
      radiusX: 1 + (working.radiusX - 1) * transition,
      radiusY: 1 + (working.radiusY - 1) * transition,
      scale: 1 + (working.scale - 1) * transition,
      opacity: chatMarkRestingOpacity + (working.opacity - chatMarkRestingOpacity) * transition,
      line: working.line * transition,
      offsetY: working.offsetY * transition
    )
  }

  private func gather(dot _: Int) -> DotFrame {
    if phase < 0.45 {
      let progress = Self.easeInOut(phase / 0.45)
      return DotFrame(
        radiusX: 1 - 0.68 * progress,
        radiusY: 1 - 0.68 * progress,
        scale: 1 + 0.24 * progress,
        opacity: 0.62 + 0.38 * progress
      )
    }
    if phase < 0.55 {
      return DotFrame(radiusX: 0.32, radiusY: 0.32, scale: 1.24, opacity: 1)
    }
    let progress = (phase - 0.55) / 0.45
    let radius = 0.32 + 0.68 * Self.easeOutBack(progress)
    return DotFrame(
      radiusX: radius,
      radiusY: radius,
      scale: 1.24 - 0.24 * Self.easeInOut(progress),
      opacity: 1
    )
  }

  private func wave(dot index: Int) -> DotFrame {
    let line = Self.bump(phase, up: 0.30, down: 0.72)
    let travel = sin(2 * .pi * phase * 2 - Double(index) * 0.9)
    return DotFrame(
      scale: 1,
      opacity: 0.55 + 0.42 * (0.5 + 0.5 * travel),
      line: line,
      offsetY: 0.13 * travel * line
    )
  }

  private static func easeInOut(_ value: Double) -> Double {
    value * value * (3 - 2 * value)
  }

  private static func easeOutBack(_ value: Double) -> Double {
    let c1 = 1.70158
    let c3 = c1 + 1
    let shifted = value - 1
    return 1 + c3 * shifted * shifted * shifted + c1 * shifted * shifted
  }

  private static func bump(_ value: Double, up: Double, down: Double) -> Double {
    if value < up { return easeInOut(value / up) }
    if value < down { return 1 }
    return 1 - easeInOut((value - down) / (1 - down))
  }
}
