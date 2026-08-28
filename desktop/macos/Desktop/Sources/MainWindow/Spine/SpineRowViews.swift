//
//  SpineRowViews.swift — the things a day is made of.
//
//  A conversation, the memories and tasks it produced, the frames that were on screen, and the map
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
//  **Air is the other half of the grid.** Rows used to sit seven points apart while `prose` set its
//  own lines six points apart, so two consecutive memories were closer to each other than a memory
//  was to itself and the column read as one grey wall. The rhythm now lives in `SpineMetrics` as
//  three values with one rule between them — a moment is far from the moment above it, an attached
//  row is close to what it came out of, and prose is set to a measure rather than to the panel.
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

  // MARK: The vertical rhythm

  /// The air above a row that is its own moment on the clock.
  ///
  /// **The number that matters is not this one, it is its ratio to the leading inside a paragraph.**
  /// `prose` sets its lines about 6 pt apart, and every row used to sit 7 pt from the one above it —
  /// so four memories at four different minutes were four paragraphs' worth of lines with no gap
  /// between them, and the eye had nothing to group by. This is over three times the line gap, which
  /// is what makes four moments read as four things.
  ///
  /// One gap, applied once, at the top of the row: the row owns the air above it and nothing else
  /// adds any, so the rhythm is a value rather than a sum of paddings scattered across four views.
  static let rowGap: CGFloat = OmiSpacing.xl
  /// The air above a row that belongs to the conversation above it. Deliberately much smaller than
  /// `rowGap` — proximity is the only thing that says a memory came out of *that* conversation, and
  /// an attached row set as far off as an unattached one has stopped being attached to anything.
  static let attachedGap: CGFloat = OmiSpacing.sm
  /// Between two memories inside one row: more than the leading, less than `rowGap`. They are
  /// separate memories, but they all came out of one conversation.
  static let memoryGap: CGFloat = OmiSpacing.md

  /// How far a memory line's hover wash bleeds past its text, so the affordance reads as a row
  /// rather than as a highlight sitting inside one.
  static let memoryHoverInset: CGFloat = OmiSpacing.sm

  /// Where the clock sits inside a row, measured from the top of that row's content, so the timestamp
  /// lands on the first line of whatever the row turned out to be.
  ///
  /// A card row (a conversation, the brain map) starts with its own padding before any type; an
  /// inline row (memories, a strip of frames) starts with the type itself. **These two are the whole
  /// of the gutter/rail correspondence**: get one wrong and the hour rail keeps tracking the right
  /// row while the times printed beside it drift off their content.
  static let cardGutterInset: CGFloat = 16
  static let inlineGutterInset: CGFloat = 3

  /// The measure a memory's sentence is set to.
  ///
  /// The panel is far wider than a paragraph wants to be. `InkLayout.contentMaxWidth` is the width
  /// `prose` was sized against — a little over sixty characters a line — and it is deliberately the
  /// existing token rather than a second opinion about how wide reading gets. **Only the prose column
  /// is capped**: the filmstrip, the conversation card and the brain map are not paragraphs and take
  /// the full lane.
  static let proseMaxWidth: CGFloat = InkLayout.contentMaxWidth
}

// MARK: - The row

/// One spine row: its place on the clock, then whatever it is.
struct SpineRowView: View {
  let row: SpineRow
  /// True while the whole spine is shown, so attached rows indent. Soloed rows pass `false` and
  /// state their own time instead.
  let showsIndent: Bool
  let onOpenConversation: (ServerConversation) -> Void
  let onOpenMemory: (SpineMemory) -> Void
  let onToggleTask: (TaskActionItem) -> Void
  let onToggleStar: (ServerConversation) -> Void
  let onOpenMoment: (SpineMoment, [SpineMoment]) -> Void
  let onShowAllMoments: () -> Void
  let onOpenBrainMap: () -> Void

  /// An attached row has no timestamp of its own while the conversation above it owns the minute;
  /// the moment it is soloed it needs one, because there is no longer anything above it to inherit.
  private var showsTimestamp: Bool { !row.isAttached }

  /// True while this row is a child of the conversation above it — which decides both how far it
  /// indents and how much air it gets, because those are the same statement made twice.
  private var isNested: Bool { row.isAttached && showsIndent }

  /// A card row starts with its own padding before any type; an inline row starts with the type.
  /// The gutter has to know which, or the clock stops landing on the content it is timing.
  private var gutterInset: CGFloat {
    switch row.content {
    case .conversation, .brainMap: return SpineMetrics.cardGutterInset
    case .memories, .tasks, .moments: return SpineMetrics.inlineGutterInset
    }
  }

  var body: some View {
    HStack(alignment: .top, spacing: 0) {
      gutter
      content
        .padding(.leading, SpineMetrics.gutterGap + (isNested ? SpineMetrics.attachmentIndent : 0))
        .frame(maxWidth: .infinity, alignment: .leading)
    }
    // The whole rhythm, in one place. Every row's content view draws from its own top edge, so the
    // gutter and the content it times are offset by the same amount and cannot drift apart.
    .padding(.top, isNested ? SpineMetrics.attachedGap : SpineMetrics.rowGap)
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
        .padding(.top, gutterInset)
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
      SpineMemoriesRow(
        memories: memories,
        showsTimestamps: !row.isAttached && !showsIndent,
        onOpen: onOpenMemory
      )
    case .tasks(let tasks):
      SpineTasksRow(
        tasks: tasks,
        showsTimestamps: !row.isAttached && !showsIndent,
        onToggle: onToggleTask
      )
    case .moments(let shown, let total):
      SpineMomentsRow(
        moments: shown, total: total, onOpen: onOpenMoment, onShowAll: onShowAllMoments)
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
  let onOpen: (SpineMemory) -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: SpineMetrics.memoryGap) {
      ForEach(memories) { memory in
        SpineMemoryLine(
          memory: memory,
          showsTimestamp: showsTimestamps && memories.count > 1,
          onOpen: { onOpen(memory) }
        )
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}

/// One memory: what kind of memory it is, quietly, over the sentence that is actually about it.
///
/// The split is `SpineFormat.memoryCopy`'s decision and its doc comment is where the reasoning lives.
/// What this view adds is the presentation: the repeated half at the small role, the sentence at the
/// reading role, and the whole thing set to one measure rather than to the width of the panel.
private struct SpineMemoryLine: View {
  let memory: SpineMemory
  let showsTimestamp: Bool
  let onOpen: () -> Void
  @State private var isHovered = false

  private var copy: SpineMemoryCopy { SpineFormat.memoryCopy(memory.text) }

  /// The dash sits on the optical centre of whichever line it is beside — derived from the role's own
  /// metrics rather than nudged by hand, so a memory with a label and one without both line up.
  private var dashInset: CGFloat {
    (copy.label == nil ? InkType.prose : InkType.statusLabel).naturalLineHeight / 2
  }

  var body: some View {
    HStack(alignment: .top, spacing: 9) {
      Rectangle()
        .fill(Ink.secondary)
        .frame(width: 6, height: 1)
        .padding(.top, dashInset)
      VStack(alignment: .leading, spacing: 2) {
        // Never line-limited: this is the user's own copy moved, not abbreviated, and a label that
        // truncates would be the one thing this split is not allowed to do.
        if let label = copy.label {
          Text(label)
            .inkStyle(.statusLabel, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
        }
        Text(copy.body)
          .inkStyle(.prose, color: Ink.secondary)
          .fixedSize(horizontal: false, vertical: true)
          .multilineTextAlignment(.leading)
        if showsTimestamp {
          Text(SpineFormat.time(memory.timestamp))
            .inkStyle(.statusLabel, color: Ink.secondary)
        }
      }
      .frame(maxWidth: SpineMetrics.proseMaxWidth, alignment: .leading)
    }
    // Two runs of one sentence: read as one utterance, not as a label and then a fragment.
    .accessibilityElement(children: .combine)
    // **A memory line used to be inert.** Every other row kind in the spine — conversation, task,
    // moment, brain map — carried an action; `.memories` shipped with none, so the one row that
    // names what Omi learned was the one row you could not open. The hit region is the whole line
    // rather than the sentence, so the dash and the timestamp are not dead pixels beside it.
    .contentShape(Rectangle())
    .onTapGesture(perform: onOpen)
    .onHover { isHovered = $0 }
    .background(
      RoundedRectangle(cornerRadius: OmiChrome.controlRadius, style: .continuous)
        .fill(isHovered ? Ink.rowFillHover : .clear)
        .padding(.horizontal, -SpineMetrics.memoryHoverInset)
    )
    .accessibilityAddTraits(.isButton)
    .accessibilityHint("Opens this memory")
    .accessibilityIdentifier("spine-memory-\(memory.id)")
  }
}

// MARK: - Tasks

/// Tasks use the same quiet inline hierarchy as memories.
struct SpineTasksRow: View {
  let tasks: [SpineTask]
  let showsTimestamps: Bool
  let onToggle: (TaskActionItem) -> Void

  var body: some View {
    VStack(alignment: .leading, spacing: SpineMetrics.memoryGap) {
      ForEach(tasks) { task in
        HStack(alignment: .top, spacing: 9) {
          Button {
            onToggle(task.task)
          } label: {
            Image(systemName: task.task.completed ? "checkmark.circle.fill" : "circle")
              .font(.system(size: 13, weight: .medium))
              .foregroundStyle(task.task.completed ? Ink.listeningGreen : Ink.secondary)
          }
          .buttonStyle(.plain)
          .help(task.task.completed ? "Mark incomplete" : "Mark complete")

          VStack(alignment: .leading, spacing: 3) {
            Text(task.text)
              .inkStyle(.prose, color: task.task.completed ? Ink.secondary : Ink.primary)
              .strikethrough(task.task.completed, color: Ink.secondary)
              .fixedSize(horizontal: false, vertical: true)
            if showsTimestamps && tasks.count > 1 {
              Text(SpineFormat.time(task.timestamp))
                .inkStyle(.statusLabel, color: Ink.secondary)
            }
          }
          .frame(maxWidth: SpineMetrics.proseMaxWidth, alignment: .leading)
        }
      }
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}

// MARK: - Screen moments

/// What was on screen, as a strip. Horizontally scrolling rather than wrapping, so a busy hour
/// never pushes the next conversation off the page.
struct SpineMomentsRow: View {
  let moments: [SpineMoment]
  let total: Int
  /// The tile that was clicked, and the strip it belongs to. The strip travels with it because the
  /// viewer steps left and right through whatever set it is given, so handing over one frame would
  /// be handing over a viewer with its arrow keys disabled.
  let onOpen: (SpineMoment, [SpineMoment]) -> Void
  /// The rest of the day, on the Rewind page. This is where navigating-to-Rewind went when
  /// clicking a tile stopped doing it: the caption is the thing that says there are 184 of these,
  /// so the caption is the honest place to offer the other 176.
  let onShowAll: () -> Void

  @State private var isHoveringCount = false

  var body: some View {
    VStack(alignment: .leading, spacing: 6) {
      // A strip that shows eight of a hundred and eighty-four and says nothing about it is a strip
      // that lies about the day — but **the count is the strip's caption and it has to look like
      // one.** Under the tiles it landed in the same column as the tiles' own captions, one line
      // below them and one line above the next row: a line belonging to neither thing it sat
      // between. Above the tiles it is unambiguously theirs, and it lands on the timestamp beside it.
      if total > moments.count {
        Button(action: onShowAll) {
          Text(
            "\(SpineFormat.number(moments.count)) of \(SpineFormat.plural(total, "moment", "moments"))"
          )
          .inkStyle(.statusLabel, color: Ink.secondary)
          .underline(isHoveringCount, pattern: .solid)
        }
        .buttonStyle(.plain)
        .onHover { isHoveringCount = $0 }
        .help("Show all of this hour in Rewind")
        .accessibilityHint(Text("Opens Rewind"))
      }
      ScrollView(.horizontal, showsIndicators: false) {
        HStack(spacing: 9) {
          ForEach(moments) { moment in
            SpineMomentTile(
              moment: moment,
              onOpen: { onOpen(moment, moments) },
              onShowAll: onShowAll)
          }
        }
        .padding(.vertical, 2)
        // The strip runs past the panel's edge, and a tile sliced off square reads as a layout
        // overflow rather than as "there is more this way".
        .padding(.trailing, SpineStripFade.width)
      }
      .mask(SpineStripFade())
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}

/// The mask that turns a clipped strip into a strip with more to the right of it.
///
/// The same technique the Rewind results panel already uses for its bottom edge
/// (`RewindSearchScrollFade`), turned on its side — deliberately the same idea rather than a second
/// opinion. **A mask and not an overlay, because the panel is glass**: there is no opaque colour to
/// fade a gradient *to*, and painting one would put a grey band down the frosting. Fading the
/// content's own alpha lets the sliced tile dissolve into the glass the panel is made of.
///
/// Applied unconditionally, for the reason `glassScrollFade` documents: a conditional modifier
/// changes the scroll view's identity every time the strip grows past one screenful, which throws
/// away the scroll position mid-scroll.
struct SpineStripFade: View {
  /// How much of the trailing edge dissolves. Wide enough to read as a fade rather than as a soft
  /// crop, narrow enough that it never eats a whole tile.
  static let width: CGFloat = 28

  var body: some View {
    GeometryReader { proxy in
      let full = max(proxy.size.width, 1)
      // Clamped so a strip narrower than the fade cannot invert the gradient.
      let start = min(max((full - Self.width) / full, 0), 1)
      LinearGradient(
        stops: [
          .init(color: .black, location: 0),
          .init(color: .black, location: start),
          .init(color: .clear, location: 1),
        ],
        startPoint: .leading,
        endPoint: .trailing)
    }
  }
}

/// One frame. Decoded downsampled and cached by `RewindThumbnailLoader`, never at full resolution —
/// a spine over a week of capture would otherwise decode gigabytes to draw 118 pt tiles.
struct SpineMomentTile: View {
  let moment: SpineMoment
  let onOpen: () -> Void
  /// The rest of the day, on the Rewind page.
  ///
  /// On the tile as well as on the caption, because the caption only exists when the strip is
  /// truncated — a row of eight or fewer moments has no caption, and without this it would have no
  /// route to Rewind at all now that clicking a tile opens the frame instead of navigating.
  let onShowAll: () -> Void

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
    .contextMenu {
      Button("Quick Look", action: onOpen)
      Divider()
      Button("Show All in Rewind", action: onShowAll)
    }
    .accessibilityLabel(Text("\(moment.label), \(moment.appName), \(SpineFormat.time(moment.timestamp))"))
    .accessibilityHint(Text("Opens this moment in Quick Look"))
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
    // The one bottom gap in the spine: the map is the last row of its day, and without it the day
    // ends flush against the next day's pinned header.
    .padding(.bottom, SpineMetrics.rowGap)
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
