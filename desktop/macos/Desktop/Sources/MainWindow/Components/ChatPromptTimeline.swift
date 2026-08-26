import OmiTheme
import SwiftUI

/// Geometry for the prompt timeline, kept pure so the placement, the collision
/// floor and the proximity ramp are all exercised without a hover.
enum ChatPromptTimelineMetrics {
  /// The strip the cursor has to enter. Wider than the marks themselves: the
  /// marks are hairlines, and a hairline is not a hover target.
  static let railWidth: CGFloat = 40
  /// The rail only earns its place where the transcript's own column is not
  /// already using the width. Sized so that a rail centred in the gutter has
  /// room to read as a deliberate navigation control.
  static let minimumGutter: CGFloat = 56

  static let restWidth: CGFloat = 8
  static let proximityWidth: CGFloat = 20
  static let hoveredWidth: CGFloat = 26
  static let markHeight: CGFloat = 2

  /// A mark nobody is pointing at is a **hairline**, and this is the alpha that makes that literal
  /// rather than aspirational.
  ///
  /// The rail's ink is `Ink.primary`, which on the light-pinned panel is near-black. At the 0.18
  /// this was tuned to on the dark palette — where the same alpha of a near-*white* ink barely lifts
  /// off the surface — a resting mark composites nearly twice as dark as `Ink.separator`, the token
  /// this app draws actual rules with. A hundred of those down the gutter is not a hairline: it is a
  /// dashed second scrollbar beside the real one, which is the exact thing the file's own doc
  /// comment says the rail must never become.
  ///
  /// So it is pinned to the app's rule weight instead of picked by eye — `separatorColor` is 0.098
  /// alpha in both appearances, and `ChatPromptTimelineTests` asserts a resting mark is no heavier
  /// than that. The reach still reads, and it reads *more*: the step from rest to proximity is now
  /// five-fold rather than under three-fold, so the marks the cursor lifts separate further from the
  /// ones it does not.
  static let restOpacity: Double = 0.098
  static let proximityOpacity: Double = 0.5
  static let hoveredOpacity: Double = 0.95
  /// The mark being read is lit, not sized. Growing it would mean the rail
  /// reshapes itself as the reader scrolls, and size is the language hover
  /// already speaks — two meanings on one channel read as noise.
  static let activeOpacity: Double = 1.0

  /// The gap between marks. They read as one object at this distance — a short
  /// stack of prompts, not a second scrollbar measuring the document.
  static let markSpacing: CGFloat = 9
  static let verticalPadding: CGFloat = 16
  /// How far up and down the rail the cursor's pull reaches, measured in marks
  /// rather than points — the group is only `markSpacing` apart, so a reach in
  /// tens of points lifts the whole stack at once and the cursor stops pointing
  /// at anything.
  static let proximityFalloff: CGFloat = markSpacing * 5
  /// Clicking or hovering resolves to a mark only within this much of it, so the
  /// empty half of a sparse rail is not a giant hit target for one tick.
  static let selectionTolerance: CGFloat = 14

  static let previewWidth: CGFloat = 236
  static let previewGap: CGFloat = 10
  static let previewEdgeInset: CGFloat = 8

  /// Keep the rail's right tip on its owning composer's edge. The Home ask bar
  /// fills its column and therefore passes zero; regular chat keeps its page
  /// margin. Marks grow leftward into the unused transcript gutter.
  static func trailingOffset(for trailingInset: CGFloat) -> CGFloat {
    max(0, trailingInset)
  }

  static let proximityAnimation: Animation = .interactiveSpring(response: 0.18, dampingFraction: 0.86)
  static let exitAnimation: Animation = .easeOut(duration: 0.18)
  static let jumpAnimation: Animation = .spring(response: 0.35, dampingFraction: 0.8)

  /// Where each mark sits: one evenly spaced group, centred on the rail.
  ///
  /// Spacing the marks by their real position in the document turns them into a
  /// second scrollbar — sparse where the answers are long, smeared into a solid
  /// bar where three questions land inside one. Grouping them says the one thing
  /// the reader wants at a glance: how many questions there are, and which one
  /// they are on. Where each prompt actually *is* is still honest, it is just
  /// carried by the active mark rather than by the spacing.
  ///
  /// A long conversation compresses rather than overflowing.
  static func positions(count: Int, railHeight: CGFloat) -> [CGFloat] {
    guard count > 0 else { return [] }
    guard count > 1 else { return [railHeight / 2] }

    let usable = max(railHeight - 2 * verticalPadding, 0)
    let spacing = min(markSpacing, usable / CGFloat(count - 1))
    let total = spacing * CGFloat(count - 1)
    let start = (railHeight - total) / 2
    return (0..<count).map { start + spacing * CGFloat($0) }
  }

  /// 1 under the cursor, decaying to exactly 0 at the edge of its reach.
  ///
  /// Quadratic. Linear swells the whole group into one breathing blob; cubic
  /// goes the other way and leaves only the mark under the cursor moving, which
  /// loses the sense of a group responding. Squared gives the run a readable
  /// order — roughly 1, 0.64, 0.36, 0.16, 0.04 across the reach — so two or
  /// three marks either side clearly participate and the rest hold still.
  static func proximity(distance: CGFloat) -> CGFloat {
    let normalized = min(max(distance, 0) / proximityFalloff, 1)
    let remaining = 1 - normalized
    return remaining * remaining
  }

  /// Width answers one question only: where is the cursor. The mark being read
  /// is the same size as every other.
  static func markWidth(isHovered: Bool, proximity: CGFloat) -> CGFloat {
    if isHovered { return hoveredWidth }
    return restWidth + (proximityWidth - restWidth) * min(max(proximity, 0), 1)
  }

  static func markOpacity(isHovered: Bool, isActive: Bool, proximity: CGFloat) -> Double {
    if isHovered { return hoveredOpacity }
    // The active mark stays fully lit, so it has to stay legible even
    // with the cursor nowhere near the rail.
    if isActive { return activeOpacity }
    return restOpacity + (proximityOpacity - restOpacity) * Double(min(max(proximity, 0), 1))
  }

  /// The rail's ink. `Ink.primary` and not white: on a light-pinned panel a white
  /// rail is invisible, and this is a mark on the surface rather than a light on it.
  static func markColor(isActive _: Bool) -> Color {
    Ink.primary
  }

  /// The mark the cursor is on, or nil in the gaps between them.
  static func index(nearest y: CGFloat, positions: [CGFloat]) -> Int? {
    var best: (index: Int, distance: CGFloat)?
    for (index, position) in positions.enumerated() {
      let distance = abs(position - y)
      if let current = best, distance >= current.distance { continue }
      best = (index, distance)
    }
    guard let best, best.distance <= selectionTolerance else { return nil }
    return best.index
  }

  /// Keeps the hover card inside the rail's height. It is mounted beside the
  /// marks rather than inside them precisely so it can overhang, but overhanging
  /// the window is a clipped card.
  static func previewCenterY(anchorY: CGFloat, cardHeight: CGFloat, railHeight: CGFloat)
    -> CGFloat
  {
    let half = cardHeight / 2 + previewEdgeInset
    guard railHeight > half * 2 else { return railHeight / 2 }
    return min(max(anchorY, half), railHeight - half)
  }
}

/// A column of hairline marks floating in the empty gutter right of the
/// transcript: one per user prompt, placed at that prompt's real position in the
/// document. Marks grow leftwards as the cursor nears them, the one being read
/// stays lit, and hovering shows the prompt with the start of its reply.
///
/// There is deliberately no track, no panel and no background. The marks sit on
/// whatever the surface already is; anything more would put a second scrollbar
/// beside the real one.
struct ChatPromptTimeline: View {
  let marks: [ChatPromptMark]
  let activeMarkID: String?
  let gutter: CGFloat
  let onSelect: (String) -> Void
  let trailingInset: CGFloat

  @State private var cursorY: CGFloat?
  @State private var hoveredMarkID: String?
  @State private var previewHeight: CGFloat = 0

  /// `hoveredIndex` seeds the hover the rail would otherwise only reach through
  /// a cursor. Production never passes it; a test cannot move a mouse, and the
  /// card's effect on the rail's own width is the thing worth pinning down.
  init(
    marks: [ChatPromptMark],
    activeMarkID: String?,
    gutter: CGFloat,
    hoveredIndex: Int? = nil,
    onSelect: @escaping (String) -> Void,
    trailingInset: CGFloat = ChatComposerLayout.pageMargin
  ) {
    self.marks = marks
    self.activeMarkID = activeMarkID
    self.gutter = gutter
    self.onSelect = onSelect
    self.trailingInset = trailingInset
    _hoveredMarkID = State(
      initialValue: hoveredIndex.flatMap { marks.indices.contains($0) ? marks[$0].id : nil }
    )
  }

  var body: some View {
    GeometryReader { geometry in
      let railHeight = geometry.size.height
      let positions = ChatPromptTimelineMetrics.positions(
        count: marks.count, railHeight: railHeight)

      ZStack(alignment: .topTrailing) {
        // The hover target. The marks are 2pt tall, so the strip is what the
        // cursor actually meets.
        Color.clear
          .contentShape(Rectangle())

        ForEach(Array(marks.enumerated()), id: \.element.id) { index, mark in
          let position = positions.indices.contains(index) ? positions[index] : 0
          markView(mark, at: position)
        }
      }
      // The card is an overlay, never a sibling. A 236pt card inside the stack
      // makes the stack 236pt wide the instant it appears, and the marks get
      // shoved out of the gutter to centre it. An overlay cannot resize what it
      // covers, so the marks hold still and the card floats over the transcript
      // the way a tooltip should.
      .overlay(alignment: .topTrailing) {
        preview(positions: positions, railHeight: railHeight)
      }
      .onContinuousHover { phase in
        switch phase {
        case .active(let location):
          OmiMotion.withGated(ChatPromptTimelineMetrics.proximityAnimation) {
            cursorY = location.y
            hoveredMarkID = Self.markID(nearest: location.y, marks: marks, positions: positions)
          }
        case .ended:
          OmiMotion.withGated(ChatPromptTimelineMetrics.exitAnimation) {
            cursorY = nil
            hoveredMarkID = nil
          }
        }
      }
      .onChange(of: marks.map(\.id)) { _, ids in
        if let cursorY {
          hoveredMarkID = Self.markID(nearest: cursorY, marks: marks, positions: positions)
        } else if let hoveredMarkID, !ids.contains(hoveredMarkID) {
          self.hoveredMarkID = nil
        }
      }
      .onTapGesture { location in
        guard let index = ChatPromptTimelineMetrics.index(nearest: location.y, positions: positions),
          marks.indices.contains(index)
        else { return }
        onSelect(marks[index].id)
      }
    }
    .frame(width: ChatPromptTimelineMetrics.railWidth, alignment: .trailing)
    .padding(.trailing, ChatPromptTimelineMetrics.trailingOffset(for: trailingInset))
    // The rail reports what the cursor is over; it never takes focus, and the
    // marks are decoration for a transcript VoiceOver already reads in order.
    .accessibilityHidden(true)
  }

  private static func markID(nearest y: CGFloat, marks: [ChatPromptMark], positions: [CGFloat])
    -> String?
  {
    guard let index = ChatPromptTimelineMetrics.index(nearest: y, positions: positions),
      marks.indices.contains(index)
    else { return nil }
    return marks[index].id
  }

  @ViewBuilder
  private func markView(_ mark: ChatPromptMark, at position: CGFloat) -> some View {
    let isHovered = hoveredMarkID == mark.id
    let isActive = activeMarkID == mark.id
    let proximity =
      cursorY.map { ChatPromptTimelineMetrics.proximity(distance: abs($0 - position)) } ?? 0
    let height = ChatPromptTimelineMetrics.markHeight

    Capsule(style: .continuous)
      .fill(
        ChatPromptTimelineMetrics.markColor(isActive: isActive)
          .opacity(
            ChatPromptTimelineMetrics.markOpacity(
              isHovered: isHovered, isActive: isActive, proximity: proximity))
      )
      .frame(
        width: ChatPromptTimelineMetrics.markWidth(isHovered: isHovered, proximity: proximity),
        height: height
      )
      // Right edge pinned, so a mark only ever grows leftwards into the gutter.
      .frame(width: ChatPromptTimelineMetrics.railWidth, alignment: .trailing)
      .offset(y: position - height / 2)
  }

  @ViewBuilder
  private func preview(positions: [CGFloat], railHeight: CGFloat) -> some View {
    if let hoveredMarkID, let index = marks.firstIndex(where: { $0.id == hoveredMarkID }),
      marks.indices.contains(index),
      positions.indices.contains(index)
    {
      VStack(alignment: .trailing, spacing: OmiSpacing.hairline) {
        ChatPromptPreviewCard(mark: marks[index])
        ChatMessageTimestamp(date: marks[index].createdAt)
      }
      .frame(width: ChatPromptTimelineMetrics.previewWidth, alignment: .trailing)
      .onGeometryChange(for: CGFloat.self) {
        $0.size.height
      } action: {
        previewHeight = $0
      }
      .offset(
        x: -(ChatPromptTimelineMetrics.railWidth + ChatPromptTimelineMetrics.previewGap),
        y: ChatPromptTimelineMetrics.previewCenterY(
          anchorY: positions[index], cardHeight: previewHeight, railHeight: railHeight)
          - previewHeight / 2
      )
      .transition(.opacity.combined(with: .scale(scale: 0.96, anchor: .trailing)))
      .allowsHitTesting(false)
    }
  }
}

/// Mounts the timeline over a transcript, and decides whether it belongs there
/// at all.
///
/// The rail is a visual overlay on the trailing edge: hairline marks, a hover
/// preview, no reserved column. The native scroll indicator stays `.never` so
/// its width cannot participate in a transcript layout feedback loop.
struct ChatPromptTimelineOverlay: View {
  @ObservedObject var geometry: ChatTranscriptGeometry
  var trailingInset: CGFloat = ChatComposerLayout.pageMargin
  let onSelect: (String) -> Void

  var body: some View {
    if geometry.showsPromptTimeline {
      ChatPromptTimeline(
        marks: geometry.marks,
        activeMarkID: geometry.activeMarkID,
        gutter: geometry.gutter,
        onSelect: select,
        trailingInset: trailingInset
      )
      .background { stepShortcuts }
    }
  }

  /// Lights the chosen mark before the scroll starts, and holds it there. The
  /// jump is animated, so waiting for the transcript to arrive would leave the
  /// rail unresponsive for the length of the spring.
  private func select(_ markID: String) {
    geometry.selectMark(markID)
    onSelect(markID)
  }

  /// ⌘↑ / ⌘↓ walk the prompts without a mouse. Zero-sized and never focusable,
  /// so they contribute a key equivalent and nothing else.
  @ViewBuilder
  private var stepShortcuts: some View {
    Group {
      shortcut(.upArrow, step: -1)
      shortcut(.downArrow, step: 1)
    }
    .opacity(0)
    .frame(width: 0, height: 0)
    .accessibilityHidden(true)
  }

  private func shortcut(_ key: KeyEquivalent, step: Int) -> some View {
    Button("") {
      guard
        let next = ChatPromptTimelineModel.steppedMarkID(
          marks: geometry.marks, from: geometry.activeMarkID, by: step)
      else { return }
      select(next)
    }
    .buttonStyle(.plain)
    .keyboardShortcut(key, modifiers: .command)
  }
}

/// What a mark is: the question, and how omi started answering it.
///
/// Built as a floating panel rather than a filled rectangle. A fill the colour of
/// the canvas *is* the canvas — the first version was a near-black card on a
/// near-black surface and read as a hole rather than as something on top.
///
/// On glass it is the app's one real floating surface (`glassFloatingBar`): the
/// `.hudWindow` material blurring the *desktop*, the ambient shadow, the faint
/// edge. Deliberately **not** SwiftUI's `.ultraThinMaterial`, which is
/// within-window vibrancy and would frost the transcript underneath instead.
private struct ChatPromptPreviewCard: View {
  let mark: ChatPromptMark

  private var shape: RoundedRectangle {
    RoundedRectangle(cornerRadius: 10, style: .continuous)
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 3) {
      Text(mark.prompt)
        .scaledFont(size: OmiType.caption, weight: .semibold)
        .foregroundColor(Ink.primary)
        .lineLimit(1)

      if !mark.reply.isEmpty {
        Text(mark.reply)
          .scaledFont(size: OmiType.caption)
          .foregroundColor(Ink.secondary)
          .lineLimit(2)
          .lineSpacing(1)
      }
    }
    .multilineTextAlignment(.leading)
    .padding(.horizontal, 11)
    .padding(.vertical, 9)
    .frame(width: ChatPromptTimelineMetrics.previewWidth, alignment: .leading)
    .glassFloatingBar(cornerRadius: 10)
    .fixedSize(horizontal: false, vertical: true)
  }
}
