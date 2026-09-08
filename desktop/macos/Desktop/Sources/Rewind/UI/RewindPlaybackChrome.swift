import AppKit
import OmiTheme
import SwiftUI

/// The visible time window of the track, and the one thing the zoom controls mutate.
///
/// A tiny observable rather than two `@State` properties on the page, because the track draws the
/// window and the buttons over the frame change it — two views a `@State` cannot span. It is the
/// single mutation point for both the buttons and the pinch, so a gesture cannot leave the track in a
/// state a button could not reach.
@MainActor
final class RewindTrackWindowModel: ObservableObject {
  @Published private(set) var start: Double = 0
  @Published private(set) var span: Double = 0

  /// The retained history's full extent. The visible window is independent and can pan anywhere in it.
  private(set) var range: ClosedRange<Double> = 0...1

  var canZoomIn: Bool { span > RewindTrackWindow.minimumSpan + 0.5 }
  var canZoomOut: Bool { span < (range.upperBound - range.lowerBound) - 0.5 }

  /// Whether `adopt` would change anything. Read from inside a SwiftUI update pass, where calling
  /// `adopt` itself would publish mid-pass.
  func needsAdoption(of newRange: ClosedRange<Double>) -> Bool {
    newRange != range || span == 0
  }

  /// Adopt the database's global bounds without forcing the viewport to show all of history at once.
  /// The first adoption starts at the already-loaded recent range; later bound extensions preserve
  /// the user's viewport.
  func adopt(range newRange: ClosedRange<Double>, initialWindow: ClosedRange<Double>? = nil) {
    guard needsAdoption(of: newRange) else { return }
    let hadWindow = span > 0
    range = newRange
    let proposed = initialWindow ?? newRange
    let clamped = RewindTrackWindow.clamp(
      start: hadWindow ? start : proposed.lowerBound,
      span: hadWindow ? span : proposed.upperBound - proposed.lowerBound,
      within: newRange)
    start = clamped.start
    span = clamped.span
  }

  func set(start newStart: Double, span newSpan: Double) {
    let clamped = RewindTrackWindow.clamp(start: newStart, span: newSpan, within: range)
    guard clamped.start != start || clamped.span != span else { return }
    start = clamped.start
    span = clamped.span
  }

  /// Zoom by a factor about the window's own centre, which is what a button press means when there is
  /// no pointer position to anchor to.
  func zoom(in zoomingIn: Bool) {
    let centre = start + span / 2
    let target = zoomingIn ? span / 2 : span * 2
    let clamped = RewindTrackWindow.clamp(start: centre - target / 2, span: target, within: range)
    set(start: clamped.start, span: clamped.span)
  }

  /// Pan continuously through time. AppKit reports a rightward content gesture as a negative
  /// horizontal delta, while the established wheel convention reports scrolling down/newer as a
  /// positive vertical delta, so the two dominant-axis paths intentionally have opposite signs.
  func pan(deltaX: CGFloat, deltaY: CGFloat, pointsPerSpan: CGFloat = 600) {
    guard span > 0, pointsPerSpan > 0 else { return }
    let movement = abs(deltaX) >= abs(deltaY) ? -deltaX : deltaY
    set(start: start + Double(movement / pointsPerSpan) * span, span: span)
  }

  /// Move the current viewport to an instant without changing its zoom level.
  func center(on instant: Double) {
    guard span > 0 else { return }
    set(start: instant - span / 2, span: span)
  }

  /// Keeps an instant inside the visible window, so stepping frames with the arrow keys cannot walk
  /// the playhead off a zoomed track.
  func reveal(_ instant: Double) {
    guard span > 0, instant < start || instant > start + span else { return }
    set(start: instant - span / 2, span: span)
  }
}

// MARK: - The track, hosted

/// Hosts `RewindTrackNSView` inside the SwiftUI chrome.
///
/// The derived shapes — capture instants, app names, contiguous blocks — are cached on the coordinator
/// and rebuilt only when the capture list actually changes. Recomputing them in `updateNSView` would
/// walk a day of rows on every scrub step, which is the shape of the cost this rebuild exists to
/// remove.
struct RewindTrackRepresentable: NSViewRepresentable {
  let screenshots: [Screenshot]
  let historyRange: ClosedRange<Double>?
  let currentIndex: Int
  let searchResultIndices: Set<Int>?
  @ObservedObject var window: RewindTrackWindowModel
  let onSelect: (Int) -> Void
  let onScroll: (CGFloat, CGFloat) -> Void

  @MainActor
  final class Coordinator {
    var signature: String = ""
    var instants: [Double] = []
    var apps: [String] = []
    var blocks: [RewindActivityBlock] = []
    var onSelect: ((Int) -> Void)?

    func refresh(_ screenshots: [Screenshot]) {
      let next = Self.signature(of: screenshots)
      guard next != signature else { return }
      signature = next
      instants = screenshots.map { $0.timestamp.timeIntervalSince1970 }
      apps = screenshots.map(\.appName)
      blocks = RewindTrackWindow.blocks(from: instants, apps: apps)
    }

    static func signature(of screenshots: [Screenshot]) -> String {
      guard let first = screenshots.first, let last = screenshots.last else { return "empty" }
      return "\(screenshots.count)|\(first.timestamp.timeIntervalSince1970)|\(last.timestamp.timeIntervalSince1970)"
    }
  }

  func makeCoordinator() -> Coordinator { Coordinator() }

  func makeNSView(context: Context) -> RewindTrackNSView {
    let view = RewindTrackNSView()
    wire(view, context: context)
    return view
  }

  func updateNSView(_ view: RewindTrackNSView, context: Context) {
    wire(view, context: context)
    let coordinator = context.coordinator
    coordinator.refresh(screenshots)

    let loadedRange = RewindTrackWindow.fullRange(of: coordinator.instants)
    let range = historyRange ?? loadedRange
    let playheadAt =
      coordinator.instants.indices.contains(currentIndex)
      ? coordinator.instants[currentIndex] : nil

    // **Scheduled, not called.** `updateNSView` runs inside SwiftUI's own update pass, and publishing
    // from there is the "Publishing changes from within view updates" defect — an observable mutated
    // mid-pass either warns or is dropped. The track adopts global bounds one turn of the run loop
    // later. The playhead deliberately does not pull a panned viewport back; explicit frame
    // navigation owns revealing it.
    if window.needsAdoption(of: range) {
      DispatchQueue.main.async {
        window.adopt(range: range, initialWindow: loadedRange)
      }
    }

    let hasWindow = window.span > 0
    view.apply(
      blocks: coordinator.blocks,
      instants: coordinator.instants,
      searchResultIndices: searchResultIndices,
      trackStart: hasWindow ? window.start : range.lowerBound,
      trackSpan: hasWindow ? window.span : range.upperBound - range.lowerBound,
      spanBounds: RewindTrackWindow
        .minimumSpan...max(
          range.upperBound - range.lowerBound, RewindTrackWindow.minimumSpan),
      playheadAt: playheadAt)
  }

  private func wire(_ view: RewindTrackNSView, context: Context) {
    // Reassigned every update: the closures capture the page's state, and a stale one would scrub a
    // list that is no longer on screen.
    context.coordinator.onSelect = onSelect
    view.onSelect = { [weak coordinator = context.coordinator] in coordinator?.onSelect?($0) }
    view.onScrubEnd = { [weak coordinator = context.coordinator] in coordinator?.onSelect?($0) }
    view.onScroll = onScroll
    view.onZoom = { [window] start, span in window.set(start: start, span: span) }
  }
}

/// The track plus the height the badges and hour labels need.
struct RewindTrackBar: View {
  let screenshots: [Screenshot]
  let historyRange: ClosedRange<Double>?
  let currentIndex: Int
  let searchResultIndices: Set<Int>?
  @ObservedObject var window: RewindTrackWindowModel
  let onSelect: (Int) -> Void
  let onScroll: (CGFloat, CGFloat) -> Void

  var body: some View {
    RewindTrackRepresentable(
      screenshots: screenshots,
      historyRange: historyRange,
      currentIndex: currentIndex,
      searchResultIndices: searchResultIndices,
      window: window,
      onSelect: onSelect,
      onScroll: onScroll
    )
    .frame(height: RewindTrackNSView.height)
    .padding(.horizontal, 18)
    .padding(.top, 4)
  }
}

// MARK: - Stage chrome

/// The controls that sit **on** the frame: the segment chevrons on its edges, the timestamp pill at
/// bottom-left and the zoom cluster at bottom-right.
///
/// **They pin to the photograph, not to the stage, and that is the whole point of the type.** The
/// chrome is an overlay on the stage, so it used to take the stage's edges — right only while the
/// picture fills the stage, which it does not. Measured on the running app at its default 1450 pt
/// window the stage is 2.55 wide against a capture's 1.81, so the picture is height-bound and there
/// is a wide band of empty glass down each side of it. The left chevron therefore sat about 200 pt
/// away from the frame it steps through, reading as a control floating on nothing rather than as the
/// frame's own edge. `RewindStageFit` answers where the picture actually is and everything here is
/// laid out inside that rectangle.
///
/// **The pill and the zoom buttons carry a material, and that is not the banned second material.**
/// `GlassContentChromeTests` holds content pages to "InkGlass is the only material in this app",
/// because a material stacked *inside* the panel reads as a muddy patch of the same glass. These
/// controls are not on the panel — they are on a photograph of somebody's screen, which can be any
/// colour at all, and a flat fill legible over a dark editor disappears over a white document. It is
/// the same exemption `glassMediaMat` already carves out for the player, for the same reason: a
/// viewport onto rendered media is not a glass surface. The chevrons take the material too now, for
/// exactly that reason — they used to sit out on the stage's margin, where `Ink.rowFill` was correct,
/// and they now sit on the picture, where it would not be.
struct RewindStageChrome: View {
  let screenshots: [Screenshot]
  let currentIndex: Int
  /// The decoded frame's own size, or nil before one has arrived. The chrome belongs to the picture,
  /// so it cannot place itself without the picture's shape.
  let imageSize: CGSize?
  @ObservedObject var window: RewindTrackWindowModel
  let onSelect: (Int) -> Void
  @Binding var showsDatePicker: Bool
  let datePicker: AnyView

  var body: some View {
    GeometryReader { proxy in
      // The overlay is applied after the stage's padding, so `proxy` is the *outer* stage and the
      // fit has to cross both spaces. `pictureRectInStage` is that composition, so this cannot get
      // half-applied.
      let picture = RewindStageFit.pictureRectInStage(image: imageSize ?? .zero, stage: proxy.size)
      controls
        .frame(width: picture.width, height: picture.height)
        .offset(x: picture.minX, y: picture.minY)
        // Nothing to belong to yet. Hidden rather than parked somewhere plausible: chrome that
        // shows up in a corner and then jumps onto the picture reads as a glitch.
        .opacity(picture.isEmpty ? 0 : 1)
        .accessibilityHidden(picture.isEmpty)
    }
  }

  private var controls: some View {
    ZStack {
      // Chevrons sit on the frame's own left and right edges.
      HStack {
        chevron(forward: false)
        Spacer(minLength: 0)
        chevron(forward: true)
      }
      .padding(.horizontal, 10)

      VStack {
        Spacer(minLength: 0)
        HStack(alignment: .bottom) {
          timestampPill
          Spacer(minLength: 0)
          controlCluster
        }
      }
      .padding(14)
    }
  }

  // MARK: Bottom-left: the date/time pill

  private var timestampPill: some View {
    Button {
      showsDatePicker.toggle()
    } label: {
      HStack(spacing: 6) {
        Image(systemName: "calendar")
          .font(.system(size: 11, weight: .medium))
        Text(timestampLabel)
          .font(.system(size: 12, weight: .medium))
        Image(systemName: "chevron.down")
          .font(.system(size: 8, weight: .bold))
          .foregroundStyle(Ink.secondary)
      }
      .foregroundStyle(Ink.primary)
      .padding(.horizontal, 11)
      .padding(.vertical, 6)
      .background(
        Capsule(style: .continuous)
          .fill(.regularMaterial)
          .overlay(Capsule(style: .continuous).strokeBorder(Ink.hairline, lineWidth: 1)))
    }
    .buttonStyle(.plain)
    .popover(isPresented: $showsDatePicker, arrowEdge: .bottom) { datePicker }
    .help("Jump to a day")
  }

  private var timestampLabel: String {
    guard screenshots.indices.contains(currentIndex) else { return "—" }
    return screenshots[currentIndex].formattedDateCompact
  }

  // MARK: Edges: one app stretch at a time

  private func chevron(forward: Bool) -> some View {
    let target = adjacentSegmentIndex(forward: forward)
    return Button {
      if let target { onSelect(target) }
    } label: {
      Image(systemName: forward ? "chevron.right" : "chevron.left")
        .font(.system(size: 13, weight: .semibold))
        .foregroundStyle(Ink.primary)
        .frame(width: 30, height: 44)
        .background(
          RoundedRectangle(cornerRadius: 8, style: .continuous)
            .fill(.regularMaterial)
            .overlay(
              RoundedRectangle(cornerRadius: 8, style: .continuous)
                .strokeBorder(Ink.hairline, lineWidth: 1)))
    }
    .buttonStyle(.plain)
    // Vanishes rather than greying out: a disabled control still advertises a step that does not
    // exist, and over a photograph a dimmed chip reads as part of the picture.
    .opacity(target == nil ? 0 : 1)
    .disabled(target == nil)
    .keyboardShortcut(forward ? .rightArrow : .leftArrow, modifiers: [.option])
    .help(forward ? "Next app" : "Previous app")
  }

  /// The first capture of the next (or previous) app stretch, or nil at either end.
  private func adjacentSegmentIndex(forward: Bool) -> Int? {
    guard screenshots.indices.contains(currentIndex) else { return nil }
    let app = screenshots[currentIndex].appName
    if forward {
      var index = currentIndex
      while index < screenshots.count, screenshots[index].appName == app { index += 1 }
      return index < screenshots.count ? index : nil
    }
    var index = currentIndex
    while index >= 0, screenshots[index].appName == app { index -= 1 }
    guard index >= 0 else { return nil }
    let previousApp = screenshots[index].appName
    while index > 0, screenshots[index - 1].appName == previousApp { index -= 1 }
    return index
  }

  // MARK: Bottom-right: the zoom cluster

  private var controlCluster: some View {
    HStack(spacing: 8) {
      circleButton(
        systemName: "minus.magnifyingglass",
        help: "Zoom the timeline out — or pinch in on the track",
        enabled: window.canZoomOut
      ) { window.zoom(in: false) }
      circleButton(
        systemName: "plus.magnifyingglass",
        help: "Zoom the timeline in — or pinch out on the track",
        enabled: window.canZoomIn
      ) { window.zoom(in: true) }
    }
  }

  private func circleButton(
    systemName: String,
    help: String,
    enabled: Bool,
    action: @escaping () -> Void
  ) -> some View {
    Button(action: action) {
      Image(systemName: systemName)
        .font(.system(size: 12, weight: .medium))
        .foregroundStyle(Ink.primary)
        .frame(width: 30, height: 30)
        .background(
          Circle()
            .fill(.regularMaterial)
            .overlay(Circle().strokeBorder(Ink.hairline, lineWidth: 1)))
    }
    .buttonStyle(.plain)
    // Dimmed rather than removed: unlike a step that does not exist, zoom is always a feature of the
    // track — the dimming reports that it has run out of range, not that it is absent.
    .opacity(enabled ? 1 : 0.45)
    .disabled(!enabled)
    .help(help)
  }
}

// MARK: - Footer

/// The line under the track: what is on screen, and how to move.
struct RewindTrackFooter: View {
  let screenshots: [Screenshot]
  let currentIndex: Int
  let showsMatchLegend: Bool

  var body: some View {
    HStack(spacing: 12) {
      if showsMatchLegend {
        HStack(spacing: 4) {
          RoundedRectangle(cornerRadius: 1)
            .fill(Color(nsColor: .systemOrange))
            .frame(width: 8, height: 8)
          Text("match")
            .font(.system(size: 10))
            .foregroundStyle(Ink.secondary)
        }
      }
      Spacer(minLength: 0)
      if screenshots.indices.contains(currentIndex) {
        Text("\(currentIndex + 1)/\(screenshots.count)")
          .font(.system(size: 10, design: .monospaced))
          .foregroundStyle(Ink.secondary)
        Text(screenshots[currentIndex].formattedDateCompact)
          .font(.system(size: 10, design: .monospaced))
          .foregroundStyle(Ink.secondary)
      }
      Text("scroll or drag to navigate")
        .font(.system(size: 10))
        .foregroundStyle(Ink.secondary)
    }
    .padding(.horizontal, 18)
    .padding(.top, 4)
    .padding(.bottom, 14)
  }
}
