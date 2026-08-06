//
//  SpineRowViews.swift — the four things a day is made of.
//
//  A conversation, the memories it produced, the frames that were on screen, and the end-of-day map
//  of what those memories connect to. They share one grid — a fixed time gutter on the left, content
//  on the right, a hairline between them — because that gutter is what makes the list a clock rather
//  than a stack of cards.
//
//  **Weight, not colour, says what is important.** The conversation is the only row with a filled
//  card and a 40 pt tile; a memory is a sentence with a tick beside it; a strip of frames is a strip
//  of frames. Nothing here is tinted to mean anything. Selection and hover are a heavier wash, per
//  the design system, and there is exactly one accent in the whole file — the star, which is the one
//  actionable thing that is not already a button.
//
//  Two type rungs only. Every one of these rows sits on glass, so `Ink.tertiary` is unavailable and
//  anything that is not `Ink.primary` is `Ink.secondary`.
//

import AppKit
import OmiTheme
import SwiftUI

// MARK: - Metrics

/// The one grid every row is laid out on.
enum SpineMetrics {
  /// The time gutter. Wide enough for "10:35 PM" at `statusLabel` without wrapping.
  static let gutterWidth: CGFloat = 68
  /// Between the gutter's hairline and the content.
  static let gutterGap: CGFloat = 16
  /// How far an attached row is indented past the conversation that produced it. Zero when one kind
  /// is soloed, which is what turns the spine back into a flat clock.
  static let attachmentIndent: CGFloat = 12
  /// The strip's thumbnail. 118 × 74 is 16:10, which is the shape of the screens these came off.
  static let thumbnailWidth: CGFloat = 118
  static let thumbnailHeight: CGFloat = 74
  /// The sticky day header's height, so the scroll reader knows what "visible" means.
  static let dayHeaderHeight: CGFloat = 34
}

// MARK: - The row

/// One spine row: its place on the clock, then whatever it is.
struct SpineRowView: View {
  let row: SpineRow
  /// True while the whole spine is shown, so attached rows indent. Soloed rows pass `false` and
  /// state their own time instead.
  let showsIndent: Bool
  let onOpenConversation: (ServerConversation) -> Void
  let onToggleStar: (ServerConversation) -> Void
  let onOpenMoment: (SpineMoment) -> Void
  let onOpenBrainMap: () -> Void

  /// An attached row has no timestamp of its own while the conversation above it owns the minute;
  /// the moment it is soloed it needs one, because there is no longer anything above it to inherit.
  private var showsTimestamp: Bool { !row.isAttached }

  var body: some View {
    HStack(alignment: .top, spacing: 0) {
      gutter
      content
        .padding(.leading, SpineMetrics.gutterGap + (row.isAttached && showsIndent ? SpineMetrics.attachmentIndent : 0))
        .frame(maxWidth: .infinity, alignment: .leading)
    }
  }

  private var gutter: some View {
    ZStack(alignment: .topTrailing) {
      // The spine's own line. It runs the full height of every row so the column is continuous
      // rather than a dashed sequence of stubs.
      HStack {
        Spacer(minLength: 0)
        Rectangle().fill(Ink.separator).frame(width: 1)
      }
      if showsTimestamp {
        HStack(spacing: 7) {
          Text(SpineFormat.time(row.anchor))
            .inkStyle(.statusLabel, color: Ink.secondary)
            .lineLimit(1)
            .fixedSize()
          // The node on the line. Only an unattached row gets one: a node per memory would make
          // the column read as a bulleted list rather than as a timeline.
          Circle()
            .fill(Ink.secondary)
            .frame(width: 5, height: 5)
            .offset(x: 3)
        }
        .padding(.top, row.kind == .conversations ? 24 : 10)
      }
    }
    .frame(width: SpineMetrics.gutterWidth, alignment: .trailing)
  }

  @ViewBuilder
  private var content: some View {
    switch row.content {
    case .conversation(let summary):
      SpineConversationRow(
        summary: summary,
        onOpen: { onOpenConversation(summary.conversation) },
        onToggleStar: { onToggleStar(summary.conversation) }
      )
    case .memories(let memories):
      SpineMemoriesRow(memories: memories, showsTimestamps: !row.isAttached && !showsIndent)
    case .moments(let shown, let total):
      SpineMomentsRow(moments: shown, total: total, onOpen: onOpenMoment)
    case .brainMap(let map):
      SpineBrainMapRow(map: map, onOpen: onOpenBrainMap)
    }
  }
}

// MARK: - Conversation

/// The dominant row. A tile, a title, what it produced, and a star.
struct SpineConversationRow: View {
  let summary: SpineConversation
  let onOpen: () -> Void
  let onToggleStar: () -> Void

  @State private var isHovering = false

  var body: some View {
    HStack(spacing: 13) {
      Text(summary.emoji)
        .font(.system(size: 19))
        .frame(width: 40, height: 40)
        .background(Circle().fill(Ink.rowFillHover))
        .overlay(Circle().strokeBorder(Ink.separator, lineWidth: 1))

      VStack(alignment: .leading, spacing: 2) {
        Text(summary.title)
          .inkStyle(.rowCopy, color: Ink.primary)
          .lineLimit(1)
          .truncationMode(.tail)
        Text(summary.subtitle)
          .inkStyle(.statusLabel, color: Ink.secondary)
          .lineLimit(1)
      }
      .frame(maxWidth: .infinity, alignment: .leading)

      SpineStarButton(isStarred: summary.isStarred, isRowHovering: isHovering, action: onToggleStar)
    }
    .padding(.horizontal, 15)
    .padding(.vertical, 12)
    .glassRow(isHovering ? .hover : .rest, cornerRadius: InkGlass.cornerRadius)
    .padding(.top, 8)
    .contentShape(Rectangle())
    .onTapGesture(perform: onOpen)
    .onHover { hovering in
      isHovering = hovering
      if hovering { NSCursor.pointingHand.push() } else { NSCursor.pop() }
    }
    .accessibilityElement(children: .combine)
    .accessibilityLabel(Text("\(summary.title). \(summary.subtitle)"))
    .accessibilityAddTraits(.isButton)
  }
}

/// The one accent in the spine, on the one thing that is actionable and is not already a button.
///
/// Hidden at rest and revealed on hover — except when it is on, because a starred conversation has
/// to say so whether or not the pointer is anywhere near it.
struct SpineStarButton: View {
  let isStarred: Bool
  let isRowHovering: Bool
  let action: () -> Void

  var body: some View {
    Button(action: action) {
      Image(systemName: isStarred ? "star.fill" : "star")
        .font(.system(size: 13, weight: .medium))
        .foregroundStyle(isStarred ? PageGlass.starred : Ink.secondary)
        .frame(width: 26, height: 26)
        .contentShape(Rectangle())
    }
    .buttonStyle(.plain)
    .opacity(isStarred || isRowHovering ? 1 : 0)
    .allowsHitTesting(isStarred || isRowHovering)
    .accessibilityLabel(Text(isStarred ? "Starred" : "Star"))
    .help(isStarred ? "Unstar" : "Star")
  }
}

// MARK: - Memories

/// What the conversation above this taught Omi. A sentence with a tick beside it — not a card,
/// because a memory is one line and a card around one line is a box around a sentence.
struct SpineMemoriesRow: View {
  let memories: [SpineMemory]
  /// Set when the row is soloed and there is no conversation above it to own the minute.
  let showsTimestamps: Bool

  var body: some View {
    VStack(alignment: .leading, spacing: 4) {
      ForEach(memories) { memory in
        HStack(alignment: .top, spacing: 9) {
          Rectangle()
            .fill(Ink.secondary)
            .frame(width: 6, height: 1)
            .padding(.top, 10)
          VStack(alignment: .leading, spacing: 1) {
            Text(memory.text)
              .inkStyle(.prose, color: Ink.secondary)
              .fixedSize(horizontal: false, vertical: true)
              .multilineTextAlignment(.leading)
            if showsTimestamps && memories.count > 1 {
              Text(SpineFormat.time(memory.timestamp))
                .inkStyle(.statusLabel, color: Ink.secondary)
            }
          }
        }
      }
    }
    .padding(.top, 7)
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}

// MARK: - Screen moments

/// What was on screen, as a strip. Horizontally scrolling rather than wrapping, so a busy hour
/// never pushes the next conversation off the page.
struct SpineMomentsRow: View {
  let moments: [SpineMoment]
  let total: Int
  let onOpen: (SpineMoment) -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      ScrollView(.horizontal, showsIndicators: false) {
        HStack(spacing: 9) {
          ForEach(moments) { moment in
            SpineMomentTile(moment: moment, onOpen: { onOpen(moment) })
          }
        }
        .padding(.vertical, 2)
      }
      // A strip that shows eight of a hundred and eighty-four and says nothing about it is a strip
      // that lies about the day.
      if total > moments.count {
        Text(
          "\(SpineFormat.number(moments.count)) of \(SpineFormat.plural(total, "moment", "moments"))"
        )
        .inkStyle(.statusLabel, color: Ink.secondary)
      }
    }
    .padding(.top, 7)
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}

/// One frame. Decoded downsampled and cached by `RewindThumbnailLoader`, never at full resolution —
/// a spine over a week of capture would otherwise decode gigabytes to draw 118 pt tiles.
struct SpineMomentTile: View {
  let moment: SpineMoment
  let onOpen: () -> Void

  @State private var image: NSImage?
  @State private var isHovering = false

  private var shape: RoundedRectangle {
    RoundedRectangle(cornerRadius: 12, style: .continuous)
  }

  var body: some View {
    Button(action: onOpen) {
      VStack(alignment: .leading, spacing: 5) {
        shape
          .fill(image == nil ? RewindPalette.color(forApp: moment.appName).opacity(0.14) : Ink.rowFill)
          .frame(width: SpineMetrics.thumbnailWidth, height: SpineMetrics.thumbnailHeight)
          .overlay {
            if let image {
              Image(nsImage: image)
                .resizable()
                .aspectRatio(contentMode: .fill)
                .frame(width: SpineMetrics.thumbnailWidth, height: SpineMetrics.thumbnailHeight)
                .clipped()
            } else {
              // **A frame with no picture is a real and common state, not a failure.** Retention
              // removes chunks, and a chunk abandoned mid-write is left zero bytes on disk — the row
              // survives, its pixels do not. A generic photo glyph says "broken image" and makes
              // every unrecoverable frame look like the same nothing.
              //
              // So it draws the app instead, through the same `AppIconView` the rest of Rewind uses:
              // the real icon when the app is installed, and `RewindPalette`'s deterministic
              // monogram disc when it is not. The moment still says *what you were in* — which is
              // most of what the picture was for — and no second empty state is invented here.
              AppIconView(appName: moment.appName, size: 26)
            }
          }
          .clipShape(shape)
          .overlay(shape.strokeBorder(isHovering ? Ink.hairline : Ink.separator, lineWidth: 1))
        Text("\(moment.appName) · \(SpineFormat.time(moment.timestamp))")
          .inkStyle(.statusLabel, color: Ink.secondary)
          .lineLimit(1)
          .truncationMode(.tail)
          .frame(width: SpineMetrics.thumbnailWidth, alignment: .leading)
      }
      .opacity(isHovering ? 0.86 : 1)
    }
    .buttonStyle(.plain)
    .onHover { isHovering = $0 }
    .help(moment.label)
    .accessibilityLabel(Text("\(moment.label), \(moment.appName), \(SpineFormat.time(moment.timestamp))"))
    .accessibilityHint(Text("Opens Rewind at this moment"))
    .task(id: moment.id) {
      // Synchronous cache hit first, so a tile scrolling back into view never flashes an empty well.
      let screenshot = moment.screenshot
      if let cached = RewindThumbnailLoader.shared.cached(screenshot) {
        image = cached
        return
      }
      image = await RewindThumbnailLoader.shared.thumbnail(for: screenshot)
    }
  }
}

// MARK: - Brain map

/// The end of a day's memories: a modest card, filed under them.
///
/// Deliberately not a destination. It is the smallest true statement about the day's memories with
/// a way into the surface that owns the graph, which is where the answer actually lives.
struct SpineBrainMapRow: View {
  let map: SpineBrainMap
  let onOpen: () -> Void

  @State private var isHovering = false

  var body: some View {
    Button(action: onOpen) {
      HStack(spacing: 16) {
        SpineBrainMapGlyph()
        VStack(alignment: .leading, spacing: 2) {
          Text(map.headline)
            .inkStyle(.rowCopy, color: Ink.primary)
          Text(map.detail)
            .inkStyle(.statusLabel, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
            .multilineTextAlignment(.leading)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        Image(systemName: "chevron.right")
          .font(.system(size: 11, weight: .semibold))
          .foregroundStyle(Ink.secondary)
      }
      .padding(.horizontal, 16)
      .padding(.vertical, 13)
      .glassRow(isHovering ? .hover : .rest, cornerRadius: InkGlass.cornerRadius)
    }
    .buttonStyle(.plain)
    .padding(.top, 10)
    .padding(.bottom, 12)
    .onHover { isHovering = $0 }
    .accessibilityLabel(Text("\(map.headline). \(map.detail)"))
  }
}

/// A little graph, drawn rather than shipped as an asset so it inherits the ink of whatever ground
/// it lands on.
struct SpineBrainMapGlyph: View {
  private static let nodes: [(x: CGFloat, y: CGFloat, r: CGFloat)] = [
    (20, 40, 3.4), (46, 22, 5), (76, 30, 3.4), (40, 54, 2.6), (84, 52, 2.6), (34, 58, 2.6),
    (68, 12, 2.6),
  ]
  private static let edges: [(Int, Int)] = [(0, 1), (1, 2), (1, 3), (2, 4), (0, 5), (1, 6)]

  var body: some View {
    Canvas { context, _ in
      var path = Path()
      for edge in Self.edges {
        path.move(to: CGPoint(x: Self.nodes[edge.0].x, y: Self.nodes[edge.0].y))
        path.addLine(to: CGPoint(x: Self.nodes[edge.1].x, y: Self.nodes[edge.1].y))
      }
      context.stroke(path, with: .color(Ink.secondary.opacity(0.45)), lineWidth: 1)
      for node in Self.nodes {
        let rect = CGRect(
          x: node.x - node.r, y: node.y - node.r, width: node.r * 2, height: node.r * 2)
        context.fill(Path(ellipseIn: rect), with: .color(Ink.secondary))
      }
    }
    .frame(width: 98, height: 66)
    .accessibilityHidden(true)
  }
}
