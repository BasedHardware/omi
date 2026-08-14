//
//  ActivityDetailView.swift — the screen a row on the spine opens into.
//
//  **It is pushed into the panel's own lower body, not into a window.** Three things decided that.
//  The panel is a borderless Spotlight surface that dies on Escape and on a click outside it; a
//  second window would survive that rule (`SearchBarWindow`'s click-away monitor only ever sees
//  clicks delivered to *other* applications, so any window of ours is structurally exempt) but it
//  would arrive with its own frame, its own level, its own glass and its own way of being closed —
//  four more things to keep in step with a panel that already resizes itself around its content.
//  A push keeps one surface, one dismissal story, and one Escape. The spine is one control away,
//  which is what the reference's own "Back" chip buys on a screen with a navigation stack.
//
//  ## What it draws, and why it is not simply the reference
//
//  The presentation is ported from Omi's own conversation detail — back chip, emoji, title, the
//  timing under it, a category chip, the account's summary, then the transcript with its speakers
//  and its offsets. Two things the reference does are deliberately dropped: the per-speaker colour
//  tints (this package ranks by weight, never by hue — see `ActivityRowViews`, and INV-UI-1), and
//  the row of destructive/editing controls (nothing on this surface writes, so a control that did
//  nothing would be worse than no control).
//
//  ## The header is what the row already knew
//
//  Title, emoji, clock and counts all travel on `ActivityConversation`, so the header is drawn
//  before any read begins and stays put whatever the read comes back with. That is what makes a
//  failed read cost the *body* and nothing else: no spinner over a blank sheet, and never a screen
//  that cannot say which conversation it failed to open.
//
//  Brand: `Ink` semantics only, two rungs (glass) — `Ink.tertiary` is unavailable here (INV-UI-1).
//

import SwiftUI

// MARK: - Metrics

/// The grid this screen is laid out on. Every number the detail draws with lives here, so the
/// rhythm is a value rather than a sum of paddings scattered across five views.
enum ActivityDetailMetrics {
    /// Either side of the header and the body. Wider than the spine's lane: this is a page to read,
    /// not a list to scan.
    static let horizontalPadding: CGFloat = 20
    static let headerTopPadding: CGFloat = 14
    static let headerBottomPadding: CGFloat = 14
    /// Between the back chip, the tile and the title block.
    static let headerGap: CGFloat = 13
    /// Inside the title block, between the overline, the headline and the timing.
    static let titleGap: CGFloat = 3
    /// Between the glyph and the word inside the back chip.
    static let backChipGap: CGFloat = 5
    static let backChipGlyphSize: CGFloat = 10

    /// The conversation's emoji disc, a step up from the row's 40 pt so the header outranks the row
    /// it was opened from.
    static let tileSize: CGFloat = 46
    static let emojiSize: CGFloat = 22
    static let glyphSize: CGFloat = 17

    /// The overline — "Conversation", "Memory", "Task" — in the day header's own idiom: uppercase
    /// and tracked out, which is what makes a word read as chrome rather than as content.
    static let overlineSize: CGFloat = 11
    static let overlineTracking: CGFloat = 1.0

    /// Between the sections of the body.
    static let sectionGap: CGFloat = 22
    /// Between a section's label and what it labels.
    static let sectionLabelGap: CGFloat = 8
    /// Between the glyph and the word in a section label.
    static let sectionGlyphGap: CGFloat = 6
    static let sectionGlyphSize: CGFloat = 11
    static let bodyTopPadding: CGFloat = 18
    static let bodyBottomPadding: CGFloat = 28

    /// The measure a paragraph is set to. The same token the spine's memory rows use, because a
    /// panel a thousand points wide is far wider than reading wants to be.
    static let proseMaxWidth: CGFloat = InkLayout.contentMaxWidth
    /// A transcript bubble's ceiling. The same measure, for the same reason.
    static let bubbleMaxWidth: CGFloat = InkLayout.contentMaxWidth

    /// The offset gutter beside a transcript line. Wide enough for "1:02:03" at `statusLabel`.
    static let offsetGutterWidth: CGFloat = 50
    static let offsetGutterGap: CGFloat = 12
    /// Between two transcript lines.
    static let lineGap: CGFloat = 14
    /// Inside a bubble.
    static let bubblePaddingHorizontal: CGFloat = 12
    static let bubblePaddingVertical: CGFloat = 8
    static let bubbleCornerRadius: CGFloat = 13
    /// Between a speaker's name and what they said.
    static let speakerGap: CGFloat = 3

    /// A chip in the header — the category, and the task's state.
    static let chipPaddingHorizontal: CGFloat = 8
    static let chipPaddingVertical: CGFloat = 3
    static let chipGap: CGFloat = 8
    static let chipGlyphSize: CGFloat = 10

    /// The empty and failed bodies: a glyph over two lines of type, centred in what is left of the
    /// panel.
    static let placeholderGlyphSize: CGFloat = 24
    static let placeholderGap: CGFloat = 8
    static let placeholderPadding: CGFloat = 28
    static let placeholderMinimumHeight: CGFloat = 220
}

// MARK: - The screen

struct ActivityDetailView: View {
    let request: ActivityDetailRequest
    /// Only ever consulted on the conversation branch — a memory and a task are already whole in the
    /// request, and a screen that reads the network to show something it is already holding is a
    /// spinner in front of an answer.
    @ObservedObject var model: ActivityDetailModel
    /// Back to the spine. Also what Escape runs — see `ActivityDetailEscape`.
    let onBack: () -> Void
    /// Opens another detail from inside this one: the conversation that was running when a memory
    /// was kept. A closure rather than a second `@State` here, so the surface stays the one place a
    /// detail is pushed.
    var onOpen: (ActivityDetailRequest) -> Void = { _ in }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Rectangle().fill(Ink.separator).frame(height: 1)
            ScrollView {
                VStack(alignment: .leading, spacing: ActivityDetailMetrics.sectionGap) {
                    switch request.subject {
                    case .conversation: conversationBody
                    case .memory, .task: contextSection
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, ActivityDetailMetrics.horizontalPadding)
                .padding(.top, ActivityDetailMetrics.bodyTopPadding)
                .padding(.bottom, ActivityDetailMetrics.bodyBottomPadding)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .accessibilityIdentifier("activity-detail")
    }

    // MARK: Header

    private var header: some View {
        HStack(alignment: .top, spacing: ActivityDetailMetrics.headerGap) {
            ActivityDetailBackChip(action: onBack)
            if case .conversation(let conversation) = request.subject {
                ActivityConversationTile(
                    emoji: conversation.emoji, size: ActivityDetailMetrics.tileSize,
                    emojiSize: ActivityDetailMetrics.emojiSize,
                    glyphSize: ActivityDetailMetrics.glyphSize)
            }
            VStack(alignment: .leading, spacing: ActivityDetailMetrics.titleGap) {
                Text(request.subject.overline.uppercased())
                    .font(
                        .system(size: ActivityDetailMetrics.overlineSize, weight: .semibold)
                    )
                    .tracking(ActivityDetailMetrics.overlineTracking)
                    .foregroundStyle(Ink.secondary)
                headline
                metaLine
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, ActivityDetailMetrics.horizontalPadding)
        .padding(.top, ActivityDetailMetrics.headerTopPadding)
        .padding(.bottom, ActivityDetailMetrics.headerBottomPadding)
    }

    /// The one line that names the thing.
    ///
    /// A conversation has a *title* — short, and the largest type on the screen. A memory and a task
    /// have a *sentence*, which is the whole of what they are: set at the same 27 pt it would run to
    /// four lines of display type, so it takes the reading role and the reading measure instead. The
    /// two are different sizes because they are different kinds of thing, not because the ladder
    /// slipped.
    @ViewBuilder
    private var headline: some View {
        switch request.subject {
        case .conversation(let conversation):
            Text(conversation.title)
                .inkStyle(.stepHeadline, color: Ink.primary)
                .lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
        case .memory(let memory):
            Text(memory.text)
                .inkStyle(.prose, color: Ink.primary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: ActivityDetailMetrics.proseMaxWidth, alignment: .leading)
        case .task(let task):
            Text(task.text)
                .inkStyle(.prose, color: task.isCompleted ? Ink.secondary : Ink.primary)
                .strikethrough(task.isCompleted, color: Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: ActivityDetailMetrics.proseMaxWidth, alignment: .leading)
        }
    }

    /// When it happened, and the one or two chips that qualify it.
    private var metaLine: some View {
        HStack(spacing: ActivityDetailMetrics.chipGap) {
            Text(timing)
                .inkStyle(.statusLabel, color: Ink.secondary)
                .lineLimit(1)
            if case .conversation = request.subject, let category = loadedBody?.category {
                ActivityDetailChip(glyph: "tag", label: category.capitalized)
            }
            if case .task(let task) = request.subject {
                ActivityDetailChip(
                    glyph: task.isCompleted ? "checkmark.circle.fill" : "circle",
                    label: task.isCompleted ? "Done" : "Open",
                    tint: task.isCompleted ? Ink.listeningGreen : Ink.secondary)
            }
        }
    }

    /// The header's clock sentence.
    ///
    /// A conversation states the day, the window it ran over and how long it took — the reference's
    /// `MMM d, yyyy from h:mm a to h:mm a`, in this app's own day vocabulary so that "Today" and
    /// "Yesterday" read the way they do everywhere else on the spine. A memory or a task states the
    /// day and the minute, which is precisely what the row could not: a row prints the time and
    /// leaves the day to the sticky header above it, and there is no header above this.
    private var timing: String {
        switch request.subject {
        case .conversation(let conversation):
            var parts = [
                ActivityFormat.day(conversation.startedAt),
                ActivityFormat.window(from: conversation.startedAt, duration: conversation.duration),
            ]
            if conversation.duration >= 1 {
                parts.append(ActivityFormat.duration(conversation.duration))
            }
            return parts.joined(separator: " · ")
        case .memory(let memory):
            return "Kept \(ActivityFormat.stamp(memory.timestamp))"
        case .task(let task):
            return "On your list for \(ActivityFormat.stamp(task.timestamp))"
        }
    }

    private var loadedBody: ActivityConversationBody? {
        guard case .read(let body) = model.state else { return nil }
        return body
    }

    // MARK: The conversation body

    @ViewBuilder
    private var conversationBody: some View {
        if let overview = loadedBody?.overview {
            VStack(alignment: .leading, spacing: ActivityDetailMetrics.sectionLabelGap) {
                ActivityDetailSectionLabel(glyph: "text.alignleft", title: "Summary")
                Text(overview)
                    .inkStyle(.prose, color: Ink.primary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: ActivityDetailMetrics.proseMaxWidth, alignment: .leading)
                    .textSelection(.enabled)
            }
        }
        VStack(alignment: .leading, spacing: ActivityDetailMetrics.sectionLabelGap) {
            ActivityDetailSectionLabel(
                glyph: "text.quote", title: "Transcript", count: loadedBody?.lines.count)
            transcript
        }
    }

    @ViewBuilder
    private var transcript: some View {
        switch model.state {
        case .reading:
            ActivityDetailPlaceholder(
                glyph: nil, headline: "Reading this conversation…", detail: nil)
        case .unread(let sentence):
            ActivityDetailPlaceholder(
                glyph: "exclamationmark.triangle", headline: sentence,
                detail: nil, retry: { model.retry() })
        case .read(let body) where body.lines.isEmpty:
            ActivityDetailPlaceholder(
                glyph: "text.quote",
                headline: isLocal ? ActivityDetailCopy.noLocalTranscript : ActivityDetailCopy.noTranscript,
                detail: isLocal ? nil : ActivityDetailCopy.noTranscriptDetail)
        case .read(let body):
            // `LazyVStack` rather than `VStack`: a long call is hundreds of lines, and this whole
            // screen sits inside one scroll view.
            LazyVStack(alignment: .leading, spacing: ActivityDetailMetrics.lineGap) {
                ForEach(body.lines) { line in
                    ActivityTranscriptRow(line: line)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var isLocal: Bool {
        guard case .conversation(let conversation) = request.subject else { return false }
        return conversation.source == .local
    }

    // MARK: The memory and task body

    /// What the spine can say about the minute a memory or a task landed in.
    ///
    /// **The caveat is part of the section, not a footnote to it.** The account's seam carries no
    /// conversation id for either kind, so the conversation shown here is the one that was *running
    /// at the time* and nothing more — and a section that showed it without saying so would be
    /// inventing provenance out of a clock, which is exactly what `ActivityComposer` refuses to do
    /// when it declines to attach these rows.
    private var contextSection: some View {
        VStack(alignment: .leading, spacing: ActivityDetailMetrics.sectionLabelGap) {
            ActivityDetailSectionLabel(
                glyph: "clock.arrow.circlepath", title: ActivityDetailCopy.contextHeading)
            if let during = request.during {
                ActivityConversationRow(
                    summary: during, onOpen: { onOpen(.conversation(during)) })
                Text(ActivityDetailCopy.contextCaveat)
                    .inkStyle(.statusLabel, color: Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: ActivityDetailMetrics.proseMaxWidth, alignment: .leading)
            } else {
                Text(ActivityDetailCopy.contextNone)
                    .inkStyle(.statusLabel, color: Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: ActivityDetailMetrics.proseMaxWidth, alignment: .leading)
            }
        }
    }
}

// MARK: - The way back

/// `‹ Activity`, wearing the same pill every other control on this panel wears.
///
/// It names the destination rather than saying "Back", because the panel has two bodies and the
/// user may have arrived at this one from either a memory or the spine — "Activity" is true of both
/// and is the word the surface is called by everywhere else.
private struct ActivityDetailBackChip: View {
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: ActivityDetailMetrics.backChipGap) {
                Image(systemName: "chevron.left")
                    .font(
                        .system(size: ActivityDetailMetrics.backChipGlyphSize, weight: .semibold))
                Text("Activity")
                    .inkStyle(.statusLabel)
                    .fixedSize()
            }
            .foregroundStyle(Ink.primary)
            .padding(.horizontal, ActivitySurfaceLayout.chipHorizontalPadding)
            .frame(height: SearchLayout.chipHeight)
            .activityChip(isSelected: false, isHovering: isHovering)
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .help("Back to Activity (Escape)")
        .accessibilityLabel(Text("Back to Activity"))
        .accessibilityIdentifier("activity-detail-back")
    }
}

// MARK: - Small parts

/// A section's name, and how many things are under it when the number is worth knowing.
private struct ActivityDetailSectionLabel: View {
    let glyph: String
    let title: String
    var count: Int?

    var body: some View {
        HStack(spacing: ActivityDetailMetrics.sectionGlyphGap) {
            Image(systemName: glyph)
                .font(.system(size: ActivityDetailMetrics.sectionGlyphSize, weight: .semibold))
                .foregroundStyle(Ink.secondary)
            Text(title)
                .inkStyle(.statusLabel, color: Ink.primary)
            if let count, count > 0 {
                Text(ActivityFormat.number(count))
                    .inkStyle(.statusLabel, color: Ink.secondary)
                    .monospacedDigit()
                    .padding(.horizontal, ActivityDetailMetrics.chipPaddingHorizontal)
                    .padding(.vertical, ActivityDetailMetrics.chipPaddingVertical)
                    .background(Capsule(style: .continuous).fill(Ink.rowFill))
            }
        }
        .accessibilityElement(children: .combine)
    }
}

/// A qualifying word in the header: the account's category, or a task's state.
private struct ActivityDetailChip: View {
    let glyph: String
    let label: String
    var tint: Color = Ink.secondary

    var body: some View {
        HStack(spacing: ActivityDetailMetrics.backChipGap) {
            Image(systemName: glyph)
                .font(.system(size: ActivityDetailMetrics.chipGlyphSize, weight: .medium))
                .foregroundStyle(tint)
            Text(label)
                .inkStyle(.statusLabel, color: Ink.secondary)
                .fixedSize()
        }
        .padding(.horizontal, ActivityDetailMetrics.chipPaddingHorizontal)
        .padding(.vertical, ActivityDetailMetrics.chipPaddingVertical)
        .background(Capsule(style: .continuous).fill(Ink.rowFill))
        .accessibilityElement(children: .combine)
    }
}

/// The body when there is no transcript to draw: still reading, could not read, or read and empty.
///
/// **One view for all three**, because they are one shape with different words — and because the
/// difference between them is a sentence, which is exactly the thing a second copy of this layout
/// would let drift.
private struct ActivityDetailPlaceholder: View {
    /// Nil while the read is running, where the spinner is the glyph.
    let glyph: String?
    let headline: String
    let detail: String?
    /// Only a failure offers one: an empty transcript will be just as empty next time.
    var retry: (() -> Void)?

    var body: some View {
        VStack(spacing: ActivityDetailMetrics.placeholderGap) {
            if let glyph {
                Image(systemName: glyph)
                    .font(.system(size: ActivityDetailMetrics.placeholderGlyphSize, weight: .regular))
                    .foregroundStyle(Ink.secondary)
            } else {
                ProgressView().controlSize(.small)
            }
            Text(headline)
                .inkStyle(.rowCopy, color: Ink.primary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            if let detail {
                Text(detail)
                    .inkStyle(.statusLabel, color: Ink.secondary)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let retry {
                Button(action: retry) {
                    Text("Try again")
                        .inkStyle(.statusLabel, color: Ink.primary)
                        .padding(.horizontal, ActivitySurfaceLayout.chipHorizontalPadding)
                        .frame(height: SearchLayout.chipHeight)
                        .activityChip(isSelected: false, isHovering: false)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("activity-detail-retry")
            }
        }
        .frame(maxWidth: ActivityDetailMetrics.proseMaxWidth)
        .frame(maxWidth: .infinity, minHeight: ActivityDetailMetrics.placeholderMinimumHeight)
        .padding(ActivityDetailMetrics.placeholderPadding)
        .accessibilityIdentifier("activity-detail-placeholder")
    }
}

// MARK: - One line of a transcript

/// A speaker, what they said, and how far into the recording they said it.
///
/// The offset sits in a gutter on the left for the same reason the spine's timestamps do: it turns a
/// column of speech into a clock you can scan. **The only thing that distinguishes the reader's own
/// voice is position and weight** — their lines sit trailing in the heavier of the two row fills.
/// The reference tints each speaker a different hue; this package ranks by weight and never by
/// colour, and a transcript is the last place to start (INV-UI-1).
struct ActivityTranscriptRow: View {
    let line: ActivityTranscriptLine

    var body: some View {
        HStack(alignment: .top, spacing: ActivityDetailMetrics.offsetGutterGap) {
            Text(ActivityFormat.offset(line.offset))
                .inkStyle(.statusLabel, color: Ink.secondary)
                .monospacedDigit()
                .lineLimit(1)
                .frame(width: ActivityDetailMetrics.offsetGutterWidth, alignment: .trailing)
            VStack(
                alignment: line.isYou ? .trailing : .leading,
                spacing: ActivityDetailMetrics.speakerGap
            ) {
                Text(line.speaker)
                    .inkStyle(.statusLabel, color: Ink.secondary)
                    .lineLimit(1)
                Text(line.text)
                    .inkStyle(.prose, color: Ink.primary)
                    .fixedSize(horizontal: false, vertical: true)
                    .multilineTextAlignment(.leading)
                    .padding(.horizontal, ActivityDetailMetrics.bubblePaddingHorizontal)
                    .padding(.vertical, ActivityDetailMetrics.bubblePaddingVertical)
                    .frame(maxWidth: ActivityDetailMetrics.bubbleMaxWidth, alignment: .leading)
                    .background(
                        RoundedRectangle(
                            cornerRadius: ActivityDetailMetrics.bubbleCornerRadius,
                            style: .continuous
                        )
                        .fill(line.isYou ? Ink.rowFillHover : Ink.rowFill))
            }
            .frame(maxWidth: .infinity, alignment: line.isYou ? .trailing : .leading)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel(Text("\(line.speaker), \(ActivityFormat.offset(line.offset)). \(line.text)"))
    }
}

// MARK: - Previews

#if DEBUG
    #Preview("Conversation detail") {
        ActivityDetailView(
            request: .conversation(
                ActivityConversation(
                    id: "c1", source: .account, title: "Pricing review with finance", emoji: "📊",
                    startedAt: Date().addingTimeInterval(-3_600), duration: 1_860,
                    overview: "We agreed to hold the enterprise tier until the beta lands.")),
            model: ActivityDetailModel(
                state: .read(
                    ActivityConversationBody(
                        overview: "We agreed to hold the enterprise tier until the beta lands.",
                        category: "work",
                        lines: [
                            ActivityTranscriptLine(
                                id: "1", speaker: "You", isYou: true,
                                text: "Where did we land on the enterprise tier?", offset: 0),
                            ActivityTranscriptLine(
                                id: "2", speaker: "Priya", isYou: false,
                                text: "Holding it until the beta ships.", offset: 7),
                        ]))),
            onBack: {}
        )
        .frame(width: 1_000, height: 580)
        .background(Ink.surface)
    }
#endif
