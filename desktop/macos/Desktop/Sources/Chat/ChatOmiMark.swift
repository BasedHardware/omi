import AppKit
import OmiTheme
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
}

enum ChatOmiMarkPlacement {
  /// The mark lives in an overlay so it never shifts an assistant bubble's
  /// leading edge. Reserve its vertical footprint in the owning row, though:
  /// an empty streaming reply otherwise has zero height and clips the mark at
  /// the transcript's live edge.
  static let reservedRowHeight: CGFloat = 32

  /// The diameter the mark is drawn at inside the transcript. The gutter is
  /// derived from it, so the two can never disagree about how much room it needs.
  static let markSize: CGFloat = 24

  /// **How much clear room the mark needs to the left of the message column.**
  ///
  /// The mark is drawn in an overlay offset by exactly this much, so a transcript hosted with less
  /// leading inset than this does not merely crowd it — it draws the mark outside the container and
  /// the assistant's only identity cue silently disappears. `ChatMessagesView` now guarantees this
  /// much leading inset itself rather than trusting each host to know the number.
  ///
  /// **It is the mark's own width plus one gap, and no more.** At `32 + md` it was 44: on the ask
  /// panel, whose content starts 16 pt in, that put the message column 60 pt from the glass while the
  /// header chip above it started at 16, and left the mark 13 pt from the panel's edge — outside
  /// every other margin on the surface and 44 pt from the sentence it labels. A gutter is the room an
  /// object needs, not a margin of its own.
  static let markGutter: CGFloat = markSize + OmiSpacing.sm

  static func rowHeight(showsMark: Bool) -> CGFloat {
    showsMark ? reservedRowHeight : 0
  }
}

struct ChatOmiMark: View {
  enum Anchor {
    case leading
    case centered
  }

  enum FrameSchedule: Equatable {
    case staticResting
    case animated(ChatMarkMotion)
  }

  var motion: ChatMarkMotion?
  var size: CGFloat = 30
  var anchor: Anchor = .leading

  @State private var model: ChatMarkModel
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  @MainActor
  init(
    motion: ChatMarkMotion?,
    size: CGFloat = 30,
    anchor: Anchor = .leading,
    model: ChatMarkModel = ChatMarkModel()
  ) {
    self.motion = motion
    self.size = size
    self.anchor = anchor
    _model = State(initialValue: model)
  }

  var body: some View {
    mark
      .frame(width: size * ChatMarkModel.widthRatio, height: size)
      .padding(.leading, anchor == .leading ? -size * ChatMarkModel.leftAnchor : 0)
      .accessibilityHidden(true)
  }

  static func frameSchedule(motion: ChatMarkMotion?, reduceMotion: Bool) -> FrameSchedule {
    guard let motion, !reduceMotion else { return .staticResting }
    return .animated(motion)
  }

  @ViewBuilder
  private var mark: some View {
    switch Self.frameSchedule(motion: motion, reduceMotion: reduceMotion) {
    case .staticResting:
      Canvas { context, canvasSize in
        model.draw(
          into: &context,
          size: canvasSize,
          base: size,
          anchor: anchor,
          resting: true
        )
      }
    case .animated(let motion):
      // Drawn by AppKit on its own timer, not by a SwiftUI `TimelineView`. A timeline frame is a SwiftUI graph update, and on
      // AppKit every graph update is rendered inside `NSHostingView.layout()`
      // — a layout pass of the whole hosting view, an AppKit walk of its
      // entire view tree and a Core Animation commit, at display refresh
      // rate, for as long as an answer streams. Measured on the mounted
      // transcript that alone kept the main thread fully busy with nothing
      // arriving. A view that redraws its own layer costs one small
      // `draw(_:)` per frame and lays nothing out.
      ChatOmiMarkAnimatedFrames(model: model, motion: motion, base: size, anchor: anchor)
    }
  }
}

/// The animated mark as an AppKit view that repaints itself on its own timer.
struct ChatOmiMarkAnimatedFrames: NSViewRepresentable {
  let model: ChatMarkModel
  let motion: ChatMarkMotion
  let base: CGFloat
  let anchor: ChatOmiMark.Anchor

  func makeNSView(context: Context) -> ChatOmiMarkFrameView {
    let view = ChatOmiMarkFrameView()
    view.configure(model: model, motion: motion, base: base, anchor: anchor)
    return view
  }

  func updateNSView(_ view: ChatOmiMarkFrameView, context: Context) {
    view.configure(model: model, motion: motion, base: base, anchor: anchor)
  }

  static func dismantleNSView(_ view: ChatOmiMarkFrameView, coordinator: ()) {
    view.stop()
  }
}

final class ChatOmiMarkFrameView: NSView {
  /// 60 Hz on the main run loop in `.common` mode, the cadence the live-edge
  /// pinner already keeps. A display link would pause with the screen, but it
  /// also never fires for a window that is not on one, which is where the
  /// mounted transcript harness lives; a timer animates wherever the view is
  /// mounted and costs one eight-dot `draw(_:)` per tick.
  private static let frameInterval: TimeInterval = 1.0 / 60.0

  private var model: ChatMarkModel?
  private var motion: ChatMarkMotion = .gather
  private var base: CGFloat = 30
  private var anchor: ChatOmiMark.Anchor = .leading
  private var timer: Timer?

  /// Top-left origin, matching the SwiftUI `Canvas` the resting frame draws in.
  override var isFlipped: Bool { true }

  override init(frame: NSRect) {
    super.init(frame: frame)
    wantsLayer = true
    layerContentsRedrawPolicy = .onSetNeedsDisplay
  }

  @available(*, unavailable)
  required init?(coder: NSCoder) { nil }

  func configure(model: ChatMarkModel, motion: ChatMarkMotion, base: CGFloat, anchor: ChatOmiMark.Anchor) {
    self.model = model
    self.motion = motion
    self.base = base
    self.anchor = anchor
    startIfNeeded()
    needsDisplay = true
  }

  override func viewDidMoveToWindow() {
    super.viewDidMoveToWindow()
    if window == nil { stop() } else { startIfNeeded() }
  }

  private func startIfNeeded() {
    guard timer == nil, window != nil else { return }
    let timer = Timer(timeInterval: Self.frameInterval, repeats: true) { [weak self] _ in
      MainActor.assumeIsolated { self?.tick() }
    }
    RunLoop.main.add(timer, forMode: .common)
    self.timer = timer
  }

  func stop() {
    timer?.invalidate()
    timer = nil
  }

  private func tick() {
    #if DEBUG
      ChatStreamingRenderProbe.hit(.markFrame)
    #endif
    model?.advance(to: Date(), motion: motion, reduceMotion: false)
    needsDisplay = true
  }

  override func draw(_ dirtyRect: NSRect) {
    guard let model, let context = NSGraphicsContext.current?.cgContext else { return }
    model.draw(in: context, size: bounds.size, base: base, anchor: anchor)
  }

  deinit {
    // An NSView's dealloc is not guaranteed to land on the main thread —
    // SwiftUI can release a representable-backed view from a background
    // queue — and an unconditional `MainActor.assumeIsolated` would trap
    // there, turning a routine teardown into a crash. The timer's block only
    // weakly captures self, so an off-main teardown costs at most one wasted
    // tick before the next `tick()` no-ops; `dismantleNSView` stops the timer
    // on the main thread for every SwiftUI-managed teardown.
    if Thread.isMainThread {
      MainActor.assumeIsolated { stop() }
    }
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

  #if DEBUG
    private(set) var debugAdvanceCount = 0
  #endif

  var snapshot: ChatMarkModelSnapshot {
    ChatMarkModelSnapshot(intensity: intensity, phase: phase, motion: motion)
  }

  func advance(to date: Date, motion requested: ChatMarkMotion?, reduceMotion: Bool) {
    #if DEBUG
      debugAdvanceCount += 1
    #endif

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
    rotation += dt * motion.spin * intensity

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

  /// One dot's place and opacity for the current frame.
  struct DotPlacement: Equatable {
    let rect: CGRect
    let opacity: Double
  }

  func draw(
    into context: inout GraphicsContext,
    size: CGSize,
    base: CGFloat,
    anchor: ChatOmiMark.Anchor,
    resting: Bool = false
  ) {
    for dot in dotPlacements(size: size, base: base, anchor: anchor, resting: resting) {
      context.fill(Path(ellipseIn: dot.rect), with: .color(Ink.primary.opacity(dot.opacity)))
    }
  }

  /// The same frame, drawn with Core Graphics for the AppKit-hosted animation.
  /// The fill is resolved through the glass's pinned appearance, not the
  /// window's: on a dark-Aqua window the transcript panel is still light, and
  /// a dynamic `labelColor` would resolve near-white there — dots on glass,
  /// invisible. The resting `Ink.primary` Canvas reads the pinned scheme
  /// through the environment; this is its AppKit twin.
  func draw(in context: CGContext, size: CGSize, base: CGFloat, anchor: ChatOmiMark.Anchor) {
    let fill = Ink.nsPrimaryOnGlass
    for dot in dotPlacements(size: size, base: base, anchor: anchor, resting: false) {
      context.setFillColor(fill.withAlphaComponent(dot.opacity).cgColor)
      context.fillEllipse(in: dot.rect)
    }
  }

  func dotPlacements(
    size: CGSize,
    base: CGFloat,
    anchor: ChatOmiMark.Anchor,
    resting: Bool
  ) -> [DotPlacement] {
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

    return (0..<Self.count).map { index in
      let frame = resting ? DotFrame() : frame(dot: index)
      let angle =
        2 * Double.pi * Double(index) / Double(Self.count)
        + Self.startAngle + (resting ? 0 : rotation)
      let ringX = centerX + ringRadius * CGFloat(frame.radiusX) * CGFloat(cos(angle))
      let ringY = centerY + ringRadius * CGFloat(frame.radiusY) * CGFloat(sin(angle))
      let lineX = lineStart + lineStep * CGFloat(index)

      let x = ringX + (lineX - ringX) * CGFloat(frame.line)
      let y =
        ringY + (centerY - ringY) * CGFloat(frame.line)
        + base * CGFloat(frame.offsetY)

      let diameter = dotDiameter * CGFloat(frame.scale)
      return DotPlacement(
        rect: CGRect(x: x - diameter / 2, y: y - diameter / 2, width: diameter, height: diameter),
        opacity: frame.opacity)
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
