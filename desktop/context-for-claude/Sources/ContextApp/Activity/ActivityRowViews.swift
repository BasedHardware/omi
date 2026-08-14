//
//  ActivityRowViews.swift — the things a day is made of.
//
//  A conversation, the memories and tasks the account kept, and the frames that were on screen while
//  it happened. They share one grid — a fixed time gutter on the left, content on the right, a
//  hairline between them — because that gutter is what makes the list a clock rather than a stack of
//  cards.
//
//  **Weight, not colour, says what is important.** The conversation is the only row with a filled
//  card; a memory is a sentence with a dash beside it; a strip of frames is a strip of frames. The
//  colours in this file are `RewindPalette`'s per-app hue behind a tile with no picture — the same
//  colour the timeline already draws that app in — and `Ink.listeningGreen` on a finished task,
//  which is the app's one "this is done" hue. Nothing else is tinted to mean anything.
//
//  Two type rungs only. Every one of these rows sits on glass, so `Ink.tertiary` is unavailable and
//  anything that is not `Ink.primary` is `Ink.secondary`.
//
//  **Air is the other half of the grid.** The rhythm lives in `ActivityMetrics` as two values with
//  one rule between them — a row is far from the row above it, and an attached row is close to what
//  it came out of. One gap, applied once, at the top of each row: the row owns the air above it and
//  nothing else adds any, so the rhythm is a value rather than a sum of paddings scattered across
//  four views.
//

import AppKit
import ContextCore
import SwiftUI

// MARK: - Metrics

/// The one grid every row is laid out on.
enum ActivityMetrics {
    /// The time gutter. Wide enough for "10:35 PM" at `statusLabel` without wrapping.
    static let gutterWidth: CGFloat = 68
    /// Between the gutter's hairline and the content.
    static let gutterGap: CGFloat = 16
    /// How far an attached row is indented past the conversation that produced it. Zero when one
    /// kind is soloed, which is what turns the list back into a flat clock.
    static let attachmentIndent: CGFloat = 12
    /// The strip's thumbnail. 118 × 74 is 16:10, which is the shape of the screens these came off.
    static let thumbnailWidth: CGFloat = 118
    static let thumbnailHeight: CGFloat = 74
    /// The sticky day header's height, so the scroll reader knows what "visible" means.
    static let dayHeaderHeight: CGFloat = 34

    // MARK: The vertical rhythm

    /// The air above a row that is its own moment on the clock.
    static let rowGap: CGFloat = 20
    /// The air above a row that belongs to the conversation above it. Deliberately much smaller
    /// than `rowGap` — proximity is the only thing that says a strip came out of *that*
    /// conversation, and an attached row set as far off as an unattached one has stopped being
    /// attached to anything.
    static let attachedGap: CGFloat = 8
    /// Between two memories, or two tasks, inside one row. More than the leading inside a paragraph
    /// and less than `rowGap`: they are separate things, but they came out of one run of the day.
    /// Set under `rowGap` and four memories read as one grey wall; set at it and the run stops being
    /// a run.
    static let itemGap: CGFloat = 12

    /// The measure a memory's or a task's sentence is set to.
    ///
    /// The panel is far wider than a paragraph wants to be. `InkLayout.contentMaxWidth` is the width
    /// `prose` was sized against — a little under eighty characters a line — and it is deliberately
    /// that existing token rather than a second opinion about how wide reading gets. **Only the
    /// prose column is capped**: the strip and the conversation card are not paragraphs and take the
    /// full lane.
    static let proseMaxWidth: CGFloat = InkLayout.contentMaxWidth

    /// The dash before a memory, and the gap between either glyph and the sentence it introduces.
    static let itemGlyphGap: CGFloat = 9
    static let memoryDashWidth: CGFloat = 6
    static let memoryDashHeight: CGFloat = 1
    /// How far the dash drops to sit on the optical centre of the line beside it. Derived from
    /// `prose`'s own metrics rather than nudged by hand, so it stays on the line if the role is
    /// retuned. The task's glyph takes none of it: a 13 pt symbol is already centred in its own box.
    static var proseGlyphInset: CGFloat { InkType.prose.naturalLineHeight / 2 }
    /// The task's tick. A glyph and not a control: `ActivityAccountReading` reads, so there is
    /// nothing here for a press to change.
    static let taskGlyphSize: CGFloat = 13
    /// Between a memory's or a task's sentence and the time under it, when a soloed row has to say
    /// its own.
    static let itemTimestampGap: CGFloat = 3
    /// How far a memory's or a task's hover fill reaches past the sentence it sits behind.
    ///
    /// **Applied as negative padding on the fill rather than as padding on the line**, so that
    /// hovering cannot move a single point of type: the gutter's clock is aligned to the first line
    /// of this content by `inlineGutterInset`, and a row that grew by five points under the pointer
    /// would slide its own timestamp off it.
    static let itemHoverInsetHorizontal: CGFloat = 8
    static let itemHoverInsetVertical: CGFloat = 5
    static let itemHoverCornerRadius: CGFloat = 9
    /// The account's emoji in the conversation tile. Sized against the 40 pt disc it sits in.
    static let conversationEmojiSize: CGFloat = 19
    /// The speech mark a local session draws instead, which has no emoji to show.
    static let conversationGlyphSize: CGFloat = 15
    /// The conversation tile.
    static let conversationTileSize: CGFloat = 40
    /// Between the tile and the type beside it.
    static let conversationTileGap: CGFloat = 13
    /// How many lines of the account's own overview a card will carry before it truncates. Two: it
    /// is a sentence about the conversation, not the conversation.
    static let overviewLineLimit = 2

    /// Where the clock sits inside a row, measured from the top of that row's content, so the
    /// timestamp lands on the first line of whatever the row turned out to be.
    ///
    /// A card row (a conversation) starts with its own padding before any type; an inline row (a
    /// strip of frames) starts with the type itself. **These two are the whole of the gutter/rail
    /// correspondence**: get one wrong and the hour rail keeps tracking the right row while the
    /// times printed beside it drift off their content.
    static let cardGutterInset: CGFloat = 16
    static let inlineGutterInset: CGFloat = 3

    /// The corner a row's card is cut to — the same radius the onboarding permission row uses, so
    /// the two surfaces read as one product.
    static let cardCornerRadius: CGFloat = 13
    /// The day header's own, a little tighter: it is a band across the lane rather than a card in it.
    static let dayHeaderCornerRadius: CGFloat = 10

    /// Between the node on the spine and the time printed beside it.
    static let gutterNodeSpacing: CGFloat = 7
    /// The node itself, and how far past the hairline it sits so it reads as being *on* the line.
    static let gutterNodeDiameter: CGFloat = 5
    static let gutterNodeOffset: CGFloat = 3

    /// Between two tiles in a strip.
    static let stripSpacing: CGFloat = 9
    /// Between the strip's caption and the tiles it captions.
    static let stripCaptionGap: CGFloat = 6
    /// Between a tile and its own caption.
    static let tileCaptionGap: CGFloat = 5
    /// The app icon a picture-less tile draws instead of a photo glyph.
    static let tileFallbackIconSize: CGFloat = 26
    /// How far a picture-less tile's colour is knocked back. It is a ground for an icon, not a chip.
    static let tileFallbackFill: Double = 0.14
    /// A tile under the pointer, so a strip says which one a click would open without moving it.
    static let tileHoverOpacity: Double = 0.86
}

// MARK: - The row

/// One row: its place on the clock, then whatever it is.
struct ActivityRowView: View {
    let row: ActivityRow
    /// True while the whole stream is shown, so attached rows indent. Soloed rows pass `false` and
    /// state their own time instead.
    let showsIndent: Bool
    let loader: FrameLoader
    let onOpenMoment: (ActivityMoment) -> Void
    /// **Every row that is not a screen moment opens a detail**, and they all leave by this one
    /// closure. A frame is the exception because it has somewhere else to be — the timeline owns
    /// pictures, and it always has.
    let onOpen: (ActivityDetailSubject) -> Void

    /// An attached row has no timestamp of its own while the conversation above it owns the minute;
    /// the moment it is soloed it needs one, because there is no longer anything above it to
    /// inherit.
    private var showsTimestamp: Bool { !row.isAttached }

    /// True while this row is a child of the conversation above it — which decides both how far it
    /// indents and how much air it gets, because those are the same statement made twice.
    private var isNested: Bool { row.isAttached && showsIndent }

    /// A card row starts with its own padding before any type; an inline row starts with the type.
    /// The gutter has to know which, or the clock stops landing on the content it is timing.
    private var gutterInset: CGFloat {
        switch row.content {
        case .conversation: return ActivityMetrics.cardGutterInset
        case .memories, .tasks, .moments: return ActivityMetrics.inlineGutterInset
        }
    }

    /// The air above this row: far from the row above it, close to what it came out of.
    private var topGap: CGFloat {
        isNested ? ActivityMetrics.attachedGap : ActivityMetrics.rowGap
    }

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            gutter
            content
                .padding(
                    .leading,
                    ActivityMetrics.gutterGap + (isNested ? ActivityMetrics.attachmentIndent : 0)
                )
                // **The air is inside the row, not above it.** Padding the `HStack` itself would put
                // the gap outside the gutter, and the spine's line — which can only run the height of
                // the view it is in — would stop at every gap and start again after it. That is the
                // dashed column of stubs the gutter exists not to be. Here the row owns its air, the
                // line runs through it, and the timestamp adds the same gap back so it still lands on
                // the first line of the content it is timing.
                .padding(.top, topGap)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var gutter: some View {
        ZStack(alignment: .topTrailing) {
            // The spine's own line. It runs the full height of every row so the column is
            // continuous rather than a dashed sequence of stubs.
            HStack {
                Spacer(minLength: 0)
                Rectangle().fill(Ink.separator).frame(width: 1)
            }
            if showsTimestamp {
                HStack(spacing: ActivityMetrics.gutterNodeSpacing) {
                    Text(ActivityFormat.time(row.anchor))
                        .inkStyle(.statusLabel, color: Ink.secondary)
                        .lineLimit(1)
                        .fixedSize()
                    // The node on the line. Only an unattached row gets one: a node per strip would
                    // make the column read as a bulleted list rather than as a timeline.
                    Circle()
                        .fill(Ink.secondary)
                        .frame(
                            width: ActivityMetrics.gutterNodeDiameter,
                            height: ActivityMetrics.gutterNodeDiameter
                        )
                        .offset(x: ActivityMetrics.gutterNodeOffset)
                }
                // The row's own air plus where the clock sits inside the content. The content adds
                // the same gap, so the two stay on one line by construction rather than by two
                // numbers that have to be kept equal by hand.
                .padding(.top, topGap + gutterInset)
            }
        }
        .frame(width: ActivityMetrics.gutterWidth, alignment: .trailing)
    }

    @ViewBuilder
    private var content: some View {
        switch row.content {
        case .conversation(let summary):
            ActivityConversationRow(summary: summary, onOpen: { onOpen(.conversation(summary)) })
        case .memories(let memories):
            // A soloed row has nothing above it owning the minute, and a run of several needs to say
            // which of them was when — one memory in a row is already timed by the gutter beside it.
            ActivityMemoriesRow(
                memories: memories, showsTimestamps: showsTimestamp,
                onOpen: { onOpen(.memory($0)) })
        case .tasks(let tasks):
            ActivityTasksRow(
                tasks: tasks, showsTimestamps: showsTimestamp, onOpen: { onOpen(.task($0)) })
        case .moments(let shown, let total):
            ActivityMomentsRow(
                moments: shown, total: total, loader: loader, onOpen: onOpenMoment)
        }
    }
}

// MARK: - Conversation

/// The dominant row. A tile, a title, and what the conversation produced.
struct ActivityConversationRow: View {
    let summary: ActivityConversation
    let onOpen: () -> Void

    @State private var isHovering = false

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: ActivityMetrics.cardCornerRadius, style: .continuous)
    }

    /// The account's own sentence about the conversation, when it wrote one and it says something.
    private var overview: String? {
        guard let trimmed = summary.overview?.trimmingCharacters(in: .whitespacesAndNewlines),
            !trimmed.isEmpty
        else { return nil }
        return trimmed
    }

    var body: some View {
        HStack(spacing: ActivityMetrics.conversationTileGap) {
            ActivityConversationTile(emoji: summary.emoji)
            VStack(alignment: .leading, spacing: 2) {
                Text(summary.title)
                    .inkStyle(.rowCopy, color: Ink.primary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                Text(summary.subtitle)
                    .inkStyle(.statusLabel, color: Ink.secondary)
                    .lineLimit(1)
                // The account's overview, when it gave one. It is under the counts rather than
                // instead of them: the counts are what this Mac and this surface know, the overview
                // is what the account thinks it was about, and neither substitutes for the other.
                if let overview {
                    Text(overview)
                        .inkStyle(.statusLabel, color: Ink.secondary)
                        .lineLimit(ActivityMetrics.overviewLineLimit)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 15)
        .padding(.vertical, 12)
        .background(shape.fill(isHovering ? Ink.rowFillHover : Ink.rowFill))
        .overlay(shape.strokeBorder(Ink.separator, lineWidth: 1))
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

/// The tile: **the account's emoji when it chose one, and the speech mark when nobody did.**
///
/// Not the app's icon. Every row on this surface is a conversation, and the app the sound came
/// through is already the first word of the title beside it — and a local session has no emoji to
/// show, so inventing one would put a glyph on the row that nothing in the record says.
///
/// A view of its own rather than a property on the row, because the detail screen opens on the same
/// conversation and has to wear the same disc a size larger — and two copies of a tile is two
/// opinions about what a conversation looks like.
struct ActivityConversationTile: View {
    let emoji: String?
    var size: CGFloat = ActivityMetrics.conversationTileSize
    var emojiSize: CGFloat = ActivityMetrics.conversationEmojiSize
    var glyphSize: CGFloat = ActivityMetrics.conversationGlyphSize

    var body: some View {
        Group {
            if let emoji {
                Text(emoji).font(.system(size: emojiSize))
            } else {
                Image(systemName: "quote.bubble")
                    .font(.system(size: glyphSize, weight: .regular))
                    .foregroundStyle(Ink.secondary)
            }
        }
        .frame(width: size, height: size)
        .background(Circle().fill(Ink.rowFillHover))
        .overlay(Circle().strokeBorder(Ink.separator, lineWidth: 1))
        .accessibilityHidden(true)
    }
}

// MARK: - Memories

/// What the account kept out of the day. A sentence with a dash beside it — not a card, because a
/// memory is one line and a card around one line is a box around a sentence.
struct ActivityMemoriesRow: View {
    let memories: [ActivityMemory]
    /// Set when the row is soloed and there is no conversation above it to own the minute.
    let showsTimestamps: Bool
    /// **Each memory in the run opens on its own**, not the run. The row groups them because they
    /// were kept in one stretch of the day; that is a reading convenience, not a thing.
    var onOpen: (ActivityMemory) -> Void = { _ in }

    var body: some View {
        VStack(alignment: .leading, spacing: ActivityMetrics.itemGap) {
            ForEach(Array(memories.enumerated()), id: \.element.id) { index, memory in
                // **The first line of a row is already timed by the gutter beside it**, which prints
                // the row's anchor — the newest memory in the run, which is this one. Giving it a
                // timestamp of its own put the same minute on screen twice, one line apart, and read
                // as a rendering fault. The rest of the run has nothing timing it, so it says its
                // own.
                ActivityItemLine(
                    showsTimestamp: showsTimestamps && index > 0, onOpen: { onOpen(memory) }
                ) {
                    Rectangle()
                        .fill(Ink.secondary)
                        .frame(
                            width: ActivityMetrics.memoryDashWidth,
                            height: ActivityMetrics.memoryDashHeight
                        )
                        .padding(.top, ActivityMetrics.proseGlyphInset)
                } timestamp: {
                    memory.timestamp
                } text: {
                    // Never line-limited: this is the user's own sentence moved, not abbreviated.
                    Text(memory.text)
                        .inkStyle(.prose, color: Ink.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// One line of a memory or task row: a glyph, then a sentence set to a measure rather than to the
/// panel, and the time under it when the gutter is not already stating it.
///
/// One view for both, because the two rows are the same shape with a different glyph — and two
/// copies of it is two places for the measure, the leading and the timestamp rule to drift.
private struct ActivityItemLine<Glyph: View, Content: View>: View {
    let showsTimestamp: Bool
    /// Opens this one thing. A sentence on the spine is worth a click for what a detail can add
    /// around it — when it was kept, and what was happening at the time — never for a larger copy
    /// of the same sentence, which is why the line itself is drawn identically either way.
    let onOpen: () -> Void
    @ViewBuilder var glyph: () -> Glyph
    var timestamp: () -> Date
    @ViewBuilder var text: () -> Content

    @State private var isHovering = false

    var body: some View {
        Button(action: onOpen) {
            HStack(alignment: .top, spacing: ActivityMetrics.itemGlyphGap) {
                glyph()
                VStack(alignment: .leading, spacing: ActivityMetrics.itemTimestampGap) {
                    text()
                        .fixedSize(horizontal: false, vertical: true)
                        .multilineTextAlignment(.leading)
                    if showsTimestamp {
                        Text(ActivityFormat.time(timestamp()))
                            .inkStyle(.statusLabel, color: Ink.secondary)
                    }
                }
                .frame(maxWidth: ActivityMetrics.proseMaxWidth, alignment: .leading)
            }
            .contentShape(Rectangle())
            .background(hoverFill)
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            isHovering = hovering
            if hovering { NSCursor.pointingHand.push() } else { NSCursor.pop() }
        }
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
    }

    /// Under the pointer, and nothing more: no card, no border, no lift. A memory is a sentence, and
    /// a box drawn round a sentence is the thing this row exists not to be.
    private var hoverFill: some View {
        RoundedRectangle(cornerRadius: ActivityMetrics.itemHoverCornerRadius, style: .continuous)
            .fill(isHovering ? Ink.rowFill : Color.clear)
            .padding(.horizontal, -ActivityMetrics.itemHoverInsetHorizontal)
            .padding(.vertical, -ActivityMetrics.itemHoverInsetVertical)
    }
}

// MARK: - Tasks

/// What the account heard you commit to. The same quiet inline hierarchy as a memory, with the tick
/// where the dash was.
///
/// **The tick is a state, not a control.** `ActivityAccountReading` has one method and it reads, so
/// there is nothing here a press could change; a button that did nothing would be worse than a glyph
/// that says what is true.
struct ActivityTasksRow: View {
    let tasks: [ActivityTask]
    let showsTimestamps: Bool
    var onOpen: (ActivityTask) -> Void = { _ in }

    var body: some View {
        VStack(alignment: .leading, spacing: ActivityMetrics.itemGap) {
            ForEach(Array(tasks.enumerated()), id: \.element.id) { index, task in
                ActivityItemLine(
                    showsTimestamp: showsTimestamps && index > 0, onOpen: { onOpen(task) }
                ) {
                    Image(systemName: task.isCompleted ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: ActivityMetrics.taskGlyphSize, weight: .medium))
                        .foregroundStyle(task.isCompleted ? Ink.listeningGreen : Ink.secondary)
                        .accessibilityHidden(true)
                } timestamp: {
                    task.timestamp
                } text: {
                    // A finished task is struck through *and* dropped a rung: either alone reads as
                    // a rendering fault rather than as "this one is done".
                    Text(task.text)
                        .inkStyle(.prose, color: task.isCompleted ? Ink.secondary : Ink.primary)
                        .strikethrough(task.isCompleted, color: Ink.secondary)
                }
                .accessibilityLabel(
                    Text(task.isCompleted ? "Done. \(task.text)" : "To do. \(task.text)"))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Screen moments

/// What was on screen, as a strip. Horizontally scrolling rather than wrapping, so a busy hour
/// never pushes the next conversation off the page.
struct ActivityMomentsRow: View {
    let moments: [ActivityMoment]
    let total: Int
    let loader: FrameLoader
    let onOpen: (ActivityMoment) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: ActivityMetrics.stripCaptionGap) {
            // A strip that shows eight of a hundred and eighty-four and says nothing about it is a
            // strip that lies about the day — but **the count is the strip's caption and it has to
            // look like one.** Under the tiles it lands in the same column as the tiles' own
            // captions, one line below them and one line above the next row: a line belonging to
            // neither thing it sits between. Above the tiles it is unambiguously theirs, and it
            // lands on the timestamp beside it.
            if total > moments.count {
                Text(
                    "\(ActivityFormat.number(moments.count)) of "
                        + ActivityFormat.plural(total, "moment", "moments")
                )
                .inkStyle(.statusLabel, color: Ink.secondary)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: ActivityMetrics.stripSpacing) {
                    ForEach(moments) { moment in
                        ActivityMomentTile(
                            moment: moment, loader: loader, onOpen: { onOpen(moment) })
                    }
                }
                .padding(.vertical, 2)
                // The strip runs past the panel's edge, and a tile sliced off square reads as a
                // layout overflow rather than as "there is more this way".
                .padding(.trailing, ActivityStripFade.width)
            }
            .mask(ActivityStripFade())
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// The mask that turns a clipped strip into a strip with more to the right of it.
///
/// **A mask and not an overlay, because the panel is glass**: there is no opaque colour to fade a
/// gradient *to*, and painting one would put a grey band down the frosting. Fading the content's own
/// alpha lets the sliced tile dissolve into the glass the panel is made of.
///
/// Applied unconditionally: a conditional modifier changes the scroll view's identity every time the
/// strip grows past one screenful, which throws away the scroll position mid-scroll.
struct ActivityStripFade: View {
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

/// One frame. Decoded and cached by `FrameLoader`, which is the app's only decoder — a strip over a
/// week of capture would otherwise decode gigabytes to draw 118 pt tiles.
struct ActivityMomentTile: View {
    let moment: ActivityMoment
    let loader: FrameLoader
    let onOpen: () -> Void

    @State private var image: NSImage?
    @State private var isHovering = false

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: 12, style: .continuous)
    }

    var body: some View {
        Button(action: onOpen) {
            VStack(alignment: .leading, spacing: ActivityMetrics.tileCaptionGap) {
                shape
                    .fill(
                        image == nil
                            ? RewindPalette.color(forApp: moment.appName)
                                .opacity(ActivityMetrics.tileFallbackFill)
                            : Ink.rowFill
                    )
                    .frame(
                        width: ActivityMetrics.thumbnailWidth,
                        height: ActivityMetrics.thumbnailHeight
                    )
                    .overlay {
                        if let image {
                            Image(nsImage: image)
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                                .frame(
                                    width: ActivityMetrics.thumbnailWidth,
                                    height: ActivityMetrics.thumbnailHeight
                                )
                                .clipped()
                        } else {
                            // **A frame with no picture is a real and common state, not a
                            // failure.** Retention unlinks files, and 8.7% of captured rows never
                            // had an image at all — the row survives, its pixels do not. A generic
                            // photo glyph says "broken image" and makes every one of those look
                            // like the same nothing.
                            //
                            // So it draws the app instead, through the same `RewindAppIcon` the
                            // timeline uses: the real icon when the app is installed, and
                            // `RewindPalette`'s deterministic monogram disc when it is not. The
                            // moment still says *what you were in* — which is most of what the
                            // picture was for — and no second empty state is invented here.
                            RewindAppIcon(
                                appName: moment.appName,
                                bundleId: moment.bundleId,
                                size: ActivityMetrics.tileFallbackIconSize)
                        }
                    }
                    .clipShape(shape)
                    .overlay(
                        shape.strokeBorder(
                            isHovering ? Ink.hairline : Ink.separator, lineWidth: 1))
                Text("\(moment.appName) · \(ActivityFormat.time(moment.timestamp))")
                    .inkStyle(.statusLabel, color: Ink.secondary)
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .frame(width: ActivityMetrics.thumbnailWidth, alignment: .leading)
            }
            .opacity(isHovering ? ActivityMetrics.tileHoverOpacity : 1)
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .help(moment.label)
        .accessibilityLabel(
            Text("\(moment.label), \(moment.appName), \(ActivityFormat.time(moment.timestamp))")
        )
        .task(id: moment.id) {
            guard let frame = moment.frame else {
                image = nil
                return
            }
            // Synchronous cache hit first, so a tile scrolling back into view never flashes an
            // empty well.
            if let cached = loader.cached(frame) {
                image = cached
                return
            }
            loader.load(frame) { decoded in
                // The tile may have been recycled onto another moment while the decode ran.
                guard self.moment.id == frame.id else { return }
                image = decoded
            }
        }
    }
}

// MARK: - Day header

/// The one place in this system where uppercase and positive tracking are justified: a header pinned
/// over moving content has to read as chrome rather than as the first line of the day.
///
/// It is also the day's **disclosure**. The whole band is the target rather than the chevron alone —
/// an 11 pt glyph is a small thing to hit repeatedly, and nothing in this header is selectable text,
/// so there is nothing for a click to be taking away. The chevron on the trailing edge is what says
/// the band is a control at all; the count beside the title is what makes a folded day still worth
/// having on screen.
struct ActivityDayHeader: View {
    let day: ActivityDay
    let isCollapsed: Bool
    let onToggle: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: onToggle) {
            HStack(spacing: 10) {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Text(day.title.uppercased())
                        .font(.system(size: 11, weight: .semibold))
                        .tracking(1.0)
                        .foregroundStyle(Ink.primary)
                    Text(day.subtitle)
                        .font(.system(size: 11, weight: .regular))
                        .foregroundStyle(Ink.secondary)
                        .lineLimit(1)
                }
                Spacer(minLength: 8)
                ActivityDayDisclosure(isCollapsed: isCollapsed, isHighlighted: isHovering)
            }
            .padding(.horizontal, 12)
            .frame(height: ActivityMetrics.dayHeaderHeight, alignment: .leading)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            isHovering = hovering
            if hovering { NSCursor.pointingHand.push() } else { NSCursor.pop() }
        }
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
        .accessibilityLabel(Text(isCollapsed ? "Expand \(day.title)" : "Collapse \(day.title)"))
        .accessibilityValue(Text(day.subtitle))
        .help(isCollapsed ? "Show this day" : "Hide this day")
        // Pinned headers have rows sliding under them, so the header has to occlude — and **a wash
        // cannot occlude.** A material is the vocabulary for exactly this: it occludes by frosting
        // what is behind it, so the header stays made of the same glass the panel is. Bounded by a
        // continuous corner and `Ink.separator` rather than bled to the edges, so it reads as a
        // band belonging to the lane instead of a slab laid across it.
        .background(
            RoundedRectangle(cornerRadius: ActivityMetrics.dayHeaderCornerRadius, style: .continuous)
                .fill(.regularMaterial)
        )
        .overlay(
            RoundedRectangle(cornerRadius: ActivityMetrics.dayHeaderCornerRadius, style: .continuous)
                .strokeBorder(Ink.separator, lineWidth: 1)
        )
        .padding(.bottom, 4)
    }
}

/// The chevron on the header's trailing edge: down for an open day, turned a quarter for a folded
/// one.
///
/// It **turns** rather than swapping glyph, because the rotation is the thing that says the two
/// states are the same control. Weight rather than colour on hover, like everything else here — and
/// the rotation animates through the gate so Reduce Motion gets the state and not the spin.
private struct ActivityDayDisclosure: View {
    let isCollapsed: Bool
    let isHighlighted: Bool

    var body: some View {
        Image(systemName: "chevron.down")
            .font(.system(size: 11, weight: .semibold))
            .foregroundStyle(isHighlighted ? Ink.primary : Ink.secondary)
            .rotationEffect(.degrees(isCollapsed ? -90 : 0))
            // Sized inside the header's own band, so a target big enough to hit without aiming
            // never makes the header taller than the scroll reader's `dayHeaderHeight` says it is.
            .frame(width: 24, height: 24)
            .animation(
                InkReduceMotion.animation(.easeOut(duration: InkMotion.stepTransition)),
                value: isCollapsed
            )
            .accessibilityHidden(true)
    }
}
