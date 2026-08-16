import OmiTheme
import SwiftUI

//  Beat 5 — the window field — and the composition that holds every beat.

// MARK: - Grid

/// Where the windows settle, where they fly in from, and how they sit once they land.
///
/// Every value is a function of the window's index, with no randomness anywhere: a cinematic that
/// looks different on each run cannot be reviewed against a screenshot.
enum OmiCinematicGrid {
  static let slots = 6
  static let columns = 3
  static let cardSize = CGSize(width: 176, height: 110)
  static let gap: CGFloat = 16

  /// The grid is exactly as wide as the prompt field above it, so the two read as one object.
  static var width: CGFloat {
    CGFloat(columns) * cardSize.width + CGFloat(columns - 1) * gap
  }

  static func rows(for count: Int) -> Int {
    guard count > 0 else { return 0 }
    return (count + columns - 1) / columns
  }

  static func height(for count: Int) -> CGFloat {
    let rows = rows(for: count)
    guard rows > 0 else { return 0 }
    return CGFloat(rows) * cardSize.height + CGFloat(rows - 1) * gap
  }

  /// The window's resting offset from the grid's centre. The last row is centred rather than
  /// left-aligned, so four windows read as a deliberate arrangement instead of a truncated one.
  static func slot(_ index: Int, count: Int) -> CGSize {
    let rowCount = rows(for: count)
    guard rowCount > 0, index < count else { return .zero }
    let row = index / columns
    let inRow = min(columns, count - row * columns)
    let column = index % columns

    let rowWidth = CGFloat(inRow) * cardSize.width + CGFloat(inRow - 1) * gap
    let x = -rowWidth / 2 + cardSize.width / 2 + CGFloat(column) * (cardSize.width + gap)

    let gridHeight = height(for: count)
    let y = -gridHeight / 2 + cardSize.height / 2 + CGFloat(row) * (cardSize.height + gap)
    return CGSize(width: x, height: y)
  }

  /// Off-screen, on a fan around the composition, so the field arrives from every direction rather
  /// than sliding in from one edge.
  static func entry(_ index: Int, count: Int, in size: CGSize) -> CGSize {
    guard count > 0 else { return .zero }
    let angle = Double(index) / Double(count) * 2 * .pi + .pi / 5
    let radius = Double(max(size.width, size.height)) * 0.78
    return CGSize(width: cos(angle) * radius, height: sin(angle) * radius)
  }

  /// The tilt a window carries while it is still in the air. Alternates side, so the field does not
  /// read as one sheet of paper folded over.
  static func entryRotation(_ index: Int) -> Double {
    let magnitude = 9 + Double(index % 3) * 4.5
    return index.isMultiple(of: 2) ? -magnitude : magnitude
  }

  /// The tilt a window keeps *after* it lands. A degree or two is the single detail that makes a
  /// set of rectangles read as a field of windows rather than as a table.
  static func restRotation(_ index: Int) -> Double {
    let magnitude = [1.5, 0.7, 1.2, 0.9, 1.6, 1.0][abs(index) % 6]
    return index.isMultiple(of: 2) ? -magnitude : magnitude
  }

  /// How large a window sits at rest. Enough that the field has a near and a far, not enough to
  /// unalign the rows.
  static func restScale(_ index: Int) -> CGFloat {
    [1.0, 0.965, 0.985, 0.955, 1.0, 0.97][abs(index) % 6]
  }

  static let nearestScale: CGFloat = 1.0
  static let farthestScale: CGFloat = 0.955

  /// How much of the float a window takes: the near ones move more than the far ones, which is
  /// parallax expressed through the same scale that sets it.
  static func depth(_ index: Int) -> CGFloat {
    let span = nearestScale - farthestScale
    guard span > 0 else { return 1 }
    let position = (restScale(index) - farthestScale) / span
    return 0.75 + position * 0.45
  }
}

// MARK: - The field

/// Every window, flying in, settling, and then floating.
struct OmiCinematicWindowGrid: View {
  let windows: [OmiCinematicWindowSpec]
  /// Windows `0..<settled` have arrived; the rest are still off-screen.
  let settled: Int
  /// The stage's size, which is what "off-screen" is measured against.
  let stageSize: CGSize
  /// Reduce Motion: no travel, no tilt, no float — just the cross-fade.
  let crossFade: Bool

  private var drifts: Bool {
    OmiCinematicWindowMotion.allowsDrift(
      crossFade: crossFade, reduceMotion: OmiMotion.reduceMotion)
  }

  var body: some View {
    Group {
      if drifts {
        // The float is a function of the clock, not a repeating animation: six independent
        // `repeatForever` springs would each own their own transaction and fight the settle, and
        // none of them could be rendered at a chosen phase for review.
        TimelineView(.animation) { context in
          field(at: context.date.timeIntervalSinceReferenceDate)
        }
      } else {
        field(at: nil)
      }
    }
    .frame(width: OmiCinematicGrid.width, height: OmiCinematicGrid.height(for: windows.count))
  }

  /// The whole field at one instant. `nil` is the static composition Reduce Motion gets.
  private func field(at time: TimeInterval?) -> some View {
    ZStack {
      ForEach(Array(windows.enumerated()), id: \.element.id) { index, spec in
        let hasArrived = index < settled
        let slot = OmiCinematicGrid.slot(index, count: windows.count)
        let entry = OmiCinematicGrid.entry(index, count: windows.count, in: stageSize)
        let drift =
          time.map {
            OmiCinematicWindowMotion.drift(
              index: index, at: $0, depth: OmiCinematicGrid.depth(index))
          } ?? .still

        OmiCinematicWindowView(spec: spec, size: OmiCinematicGrid.cardSize)
          .rotationEffect(.degrees(OmiCinematicGrid.restRotation(index) + drift.rotation))
          .scaleEffect(OmiCinematicGrid.restScale(index))
          .offset(x: drift.dx, y: drift.dy)
          // The float updates every frame and must never be animated: inside the settle spring's
          // transaction it would lag a frame behind itself and smear.
          .transaction { $0.animation = nil }
          .rotationEffect(
            .degrees(hasArrived || crossFade ? 0 : OmiCinematicGrid.entryRotation(index))
          )
          .scaleEffect(hasArrived ? 1 : (crossFade ? 1 : 0.84))
          .offset(
            x: hasArrived || crossFade ? slot.width : slot.width + entry.width,
            y: hasArrived || crossFade ? slot.height : slot.height + entry.height
          )
          .opacity(hasArrived ? 1 : 0)
      }
    }
  }
}

// MARK: - The composition

/// The whole cinematic: the scrim, the one object beats 2–4 build, the window field, and the two
/// controls that can stop it.
struct OmiCinematicView: View {
  @ObservedObject var director: OmiCinematicDirector

  /// The layout every metric in `OmiCinematicVesselMetrics` and `OmiCinematicGrid` was authored
  /// against. The composition is scaled to the display rather than laid out for it, so a 13" panel
  /// and a 5K display get the same picture at different sizes.
  nonisolated static let designSize = CGSize(width: 700, height: 470)

  /// Where onboarding will land: slightly above true centre, so that is where beat 6 recedes to.
  static let panelAnchor = UnitPoint(x: 0.5, y: 0.45)

  /// Between the prompt field and the top of the field.
  static let gridGap: CGFloat = 30

  var body: some View {
    GeometryReader { geometry in
      ZStack {
        OmiCinematicPalette.scrim
          .opacity(director.dim)

        composition(in: geometry.size)
          .scaleEffect(
            Self.scale(for: geometry.size) * (director.receding ? 0.66 : 1),
            anchor: Self.panelAnchor
          )
          .opacity(director.receding ? 0 : 1)

        controls
      }
      .frame(width: geometry.size.width, height: geometry.size.height)
    }
    .ignoresSafeArea()
    // The scrim is the click target for nothing at all, but it must not let a click through to
    // whatever is behind it either — the desktop is dimmed because it is not part of this.
    .contentShape(Rectangle())
  }

  /// The vessel and the field, positioned as one block so opening the field lifts the prompt rather
  /// than pushing it off centre.
  private func composition(in stageSize: CGSize) -> some View {
    let count = director.windows.count
    let gridHeight = director.gridOpen ? OmiCinematicGrid.height(for: count) : 0
    let blockHeight = OmiCinematicVesselMetrics.promptShellHeight + Self.gridGap + gridHeight
    let vesselY =
      director.gridOpen ? -(blockHeight - OmiCinematicVesselMetrics.promptShellHeight) / 2 : 0
    let gridY = (blockHeight - gridHeight) / 2

    return ZStack {
      OmiCinematicWindowGrid(
        windows: director.windows,
        settled: director.settledCards,
        stageSize: stageSize,
        crossFade: director.timing.isCrossFade
      )
      .opacity(director.gridOpen ? 1 : 0)
      .offset(y: gridY)

      OmiCinematicVessel(
        draw: director.draw,
        form: director.form,
        pulsing: director.pulsing,
        question: director.typedQuestion,
        showsCaret: director.showsCaret,
        animatesCaret: !director.timing.isCrossFade
      )
      .offset(y: vesselY)
    }
    .frame(width: Self.designSize.width, height: Self.designSize.height)
  }

  /// "Skip intro", and the bed's own mute control.
  ///
  /// The bed is content rather than chrome, so the system's UI-sound switch does not govern it —
  /// this is the explicit control that does, and it persists.
  private var controls: some View {
    VStack {
      Spacer()
      HStack(spacing: 14) {
        Button(action: director.toggleMusic) {
          Image(systemName: director.musicEnabled ? "speaker.wave.2" : "speaker.slash")
            .font(.system(size: 12, weight: .medium))
            .frame(width: 30, height: 30)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(OmiCinematicPalette.inkSecondary)
        .accessibilityLabel(Text(director.musicEnabled ? "Mute music" : "Unmute music"))

        Button(action: director.skip) {
          Text(verbatim: "Skip intro")
            .geist(size: 12, weight: .medium)
            .foregroundStyle(OmiCinematicPalette.inkSecondary)
            .padding(.horizontal, 14)
            .frame(height: 30)
            .overlay(
              Capsule(style: .continuous)
                .strokeBorder(OmiCinematicPalette.hairline, lineWidth: 1)
            )
            .contentShape(Capsule(style: .continuous))
        }
        .buttonStyle(.plain)
        // Esc. The window also carries a key monitor, because a borderless window is not guaranteed
        // to be the one AppKit routes `cancelAction` to.
        .keyboardShortcut(.cancelAction)
      }
      .padding(.bottom, 44)
      // Arrives with the dim rather than before it, and leaves with beat 6 — a "Skip intro" button
      // hanging over the field would be pointing at nothing.
      .opacity(Self.controlsVisible(dim: director.dim, receding: director.receding) ? 1 : 0)
      .omiAnimation(
        .easeOut(duration: OmiCinematicTiming.crossFade),
        value: Self.controlsVisible(dim: director.dim, receding: director.receding))
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
  }

  /// The controls follow the scrim in and leave with beat 6.
  ///
  /// `nonisolated` so the rule is a value a test can assert without a main-actor hop: SwiftUI infers
  /// main-actor isolation for members of a `View`, and this is pure arithmetic.
  nonisolated static func controlsVisible(dim: Double, receding: Bool) -> Bool {
    dim > 0.35 && !receding
  }

  /// Floored so a small window still reads, capped so a 5K display does not turn the prompt field
  /// into a billboard. `nonisolated` for the same reason as `controlsVisible`.
  nonisolated static func scale(for size: CGSize) -> CGFloat {
    guard size.width > 0, size.height > 0 else { return 1 }
    let fit = min(
      size.width / designSize.width,
      size.height / designSize.height)
    return min(max(fit * 0.92, 0.78), 1.5)
  }
}
