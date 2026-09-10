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
    .padding(.horizontal, RewindStageFit.horizontalInset)
    .padding(.top, Self.topPadding)
  }

  /// The air above the track. Published so the control bar above it can close the gap to the same
  /// distance the stage keeps on its other side.
  nonisolated static let topPadding: CGFloat = 4
}

// MARK: - App steps

/// One app stretch at a time: where the previous and the next stretch begin, as a pure function so
/// the stepping is a test rather than a click.
enum RewindAppStep {
  /// The first capture of the next (or previous) app stretch, or nil at either end. Backward lands on
  /// the *start* of the previous stretch, not its last frame, so two presses walk two apps back
  /// rather than one press per frame.
  static func adjacentSegmentIndex(in screenshots: [Screenshot], from currentIndex: Int, forward: Bool)
    -> Int?
  {
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
}

// MARK: - Stage control bar

/// Where the row of controls under the picture sits, as values a test can hold rather than literals
/// inside a `body`.
///
/// The row shares the stage's horizontal inset and the track's, so the pill's leading edge, the
/// stage's leading edge and the track's leading edge are one line down the panel. A row inset
/// differently from the objects above and below it reads as belonging to neither.
enum RewindStageControlBarLayout {
  /// Delegated to the stage, never restated: the picture and its controls keep one margin.
  static var horizontalInset: CGFloat { RewindStageFit.horizontalInset }

  /// The control height. The pill, the app-step circles and the zoom circles are all this tall so
  /// the row has one baseline and the three families read as one.
  static let controlHeight: CGFloat = 30

  /// The air between two circles that belong together — the previous/next pair, the zoom pair.
  static let pairSpacing: CGFloat = 8

  /// The air under the row, before the track's own top padding. The stage already carries its
  /// `verticalInset` above the row, so the row sits the same distance from the picture as it does
  /// from the track.
  static var bottomGap: CGFloat { RewindStageFit.verticalInset - RewindTrackBar.topPadding }
}

/// The row on the glass directly under the picture: the date pill at the leading edge, the
/// previous/next app circles in the centre, the zoom cluster at the trailing edge.
///
/// **Nothing sits on the photograph any more.** The pill and the zoom cluster used to live in the
/// picture's bottom corners and the app-step chevrons on its left and right edges — all of them
/// over whatever the capture happened to show there, a menu bar, a status line, the very text
/// someone scrubbed to. A control over the content it hides is a control in the wrong place, so
/// the whole set is one row beneath the picture, and the picture is only the picture.
///
/// **On the panel, so on the panel's fills.** Over a photograph these controls needed a system
/// material to stay legible against any colour a capture could show. Under the picture they are on
/// `InkGlass` like every other control on a content page, and a material stacked inside the panel
/// is exactly the muddy second glass `GlassContentChromeTests` forbids — so every control here is
/// `Ink.rowFill` under a hairline, the same dress as the rest of the page's chrome. The app-step
/// buttons are the same circle as the zoom buttons, not a taller chip: one shape for one row.
struct RewindStageControlBar: View {
  let screenshots: [Screenshot]
  let currentIndex: Int
  @ObservedObject var window: RewindTrackWindowModel
  @Binding var showsDatePicker: Bool
  let datePicker: AnyView
  let onSelect: (Int) -> Void

  var body: some View {
    HStack(alignment: .center) {
      timestampPill
      Spacer(minLength: 0)
      controlCluster
    }
    // Centred on the row, not between the pill and the zoom cluster: the pill's width changes with
    // the date, and a pair that drifted with it would never sit under the picture's middle.
    .overlay { appSteps }
    .padding(.horizontal, RewindStageControlBarLayout.horizontalInset)
    .padding(.bottom, RewindStageControlBarLayout.bottomGap)
  }

  // MARK: Leading: the date/time pill

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
      .frame(height: RewindStageControlBarLayout.controlHeight)
      .background(
        Capsule(style: .continuous)
          .fill(Ink.rowFill)
          .overlay(Capsule(style: .continuous).strokeBorder(Ink.hairline, lineWidth: 1)))
    }
    .buttonStyle(.plain)
    // Opens upward, over the picture: the track under the row is what the user is about to scrub,
    // and a popover that lands on it hides the thing the date it picks will move.
    .popover(isPresented: $showsDatePicker, arrowEdge: .top) { datePicker }
    .help("Jump to a day")
  }

  private var timestampLabel: String {
    guard screenshots.indices.contains(currentIndex) else { return "—" }
    return screenshots[currentIndex].formattedDateCompact
  }

  // MARK: Centre: one app stretch at a time

  private var appSteps: some View {
    HStack(spacing: RewindStageControlBarLayout.pairSpacing) {
      appStep(forward: false)
      appStep(forward: true)
    }
  }

  private func appStep(forward: Bool) -> some View {
    let target = RewindAppStep.adjacentSegmentIndex(in: screenshots, from: currentIndex, forward: forward)
    return circleButton(
      systemName: forward ? "chevron.right" : "chevron.left",
      help: forward ? "Next app" : "Previous app",
      enabled: target != nil
    ) {
      if let target { onSelect(target) }
    }
    .keyboardShortcut(forward ? .rightArrow : .leftArrow, modifiers: [.option])
  }

  // MARK: Trailing: the zoom cluster

  private var controlCluster: some View {
    HStack(spacing: RewindStageControlBarLayout.pairSpacing) {
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

  /// The row's one button shape: a glass circle, `controlHeight` across.
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
        .frame(
          width: RewindStageControlBarLayout.controlHeight,
          height: RewindStageControlBarLayout.controlHeight
        )
        .background(
          Circle()
            .fill(Ink.rowFill)
            .overlay(Circle().strokeBorder(Ink.hairline, lineWidth: 1)))
    }
    .buttonStyle(.plain)
    // Dimmed rather than removed. On the glass a missing circle leaves a hole in a pair, and the
    // dimming reports that the step or the zoom has run out of range, not that it is absent.
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
