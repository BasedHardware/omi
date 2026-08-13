//
//  ActivityRowViews.swift — the things a day is made of.
//
//  A conversation and the frames that were on screen while it happened. They share one grid — a
//  fixed time gutter on the left, content on the right, a hairline between them — because that
//  gutter is what makes the list a clock rather than a stack of cards.
//
//  **Weight, not colour, says what is important.** The conversation is the only row with a filled
//  card; a strip of frames is a strip of frames. The single colour in the file is
//  `RewindPalette`'s per-app hue behind a tile with no picture, which is the same colour the
//  timeline already draws that app in — nothing here is tinted to mean anything else.
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
    let onOpenConversation: (ActivityConversation) -> Void

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
        case .moments: return ActivityMetrics.inlineGutterInset
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
            ActivityConversationRow(summary: summary, onOpen: { onOpenConversation(summary) })
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

    var body: some View {
        HStack(spacing: 13) {
            // A speech mark rather than the app's icon: every row on this surface is a
            // conversation, and the app the sound came through is already the first word of the
            // title beside it.
            Image(systemName: "quote.bubble")
                .font(.system(size: 15, weight: .regular))
                .foregroundStyle(Ink.secondary)
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
            Text("\(moment.label), \(moment.appName), \(ActivityFormat.time(moment.timestamp))"))
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
                value: isCollapsed)
            .accessibilityHidden(true)
    }
}
