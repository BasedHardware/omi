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
//  ## What it draws: the reference's information architecture, in this app's tokens
//
//  This is Omi's own conversation detail (`MainWindow/Pages/ConversationDetailView.swift`) ported
//  section for section and in its order. A conversation opens on its **summary**:
//
//      header  ·  back · emoji · title · when it ran ·  [status]  [View Transcript]
//      ─────────────────────────────────────────────────────────────────────────────
//      processing notice        while the account is still working, or has given up
//      Summary                  the account's overview
//      chips                    where it was captured · how long · its category
//      App Insights             what installed apps made of it
//      Action Items             each with a way through to the lines it came from
//
//  …and the transcript sits behind the header's button, in a pane of its own. That exclusivity is
//  the reference's, and its reason is ours too: at 580 pt of panel a summary and a transcript side
//  by side are two columns neither of which can be read in.
//
//  Three of the reference's sections are **deliberately not here**, because they are controls for
//  capabilities this app does not have rather than content it is withholding: reprocessing a
//  conversation with an app, the "Try with Apps" rail, and the app-selector sheet all need the app
//  catalog and the write endpoints, and its editing toolbar (rename, delete, move to folder, share
//  link) writes to a record this surface only reads. The per-speaker colour tints are dropped too:
//  this package ranks by weight and never by hue (INV-UI-1). Nothing is left as a dead section.
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

import AppKit
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

    /// The highlight behind a line an action item pointed at. Insets rather than a fill on the
    /// bubble, so the mark reads as "this row" and cannot be confused with the heavier fill that
    /// already distinguishes the reader's own voice.
    static let focusInsetHorizontal: CGFloat = 10
    static let focusInsetVertical: CGFloat = 6
    static let focusCornerRadius: CGFloat = 11

    /// A chip in the header — the category, the source, the status, and the task's state.
    static let chipPaddingHorizontal: CGFloat = 8
    static let chipPaddingVertical: CGFloat = 3
    static let chipGap: CGFloat = 8
    static let chipGlyphSize: CGFloat = 10

    /// A card: an action item, an app's reading, the processing notice. One radius for all three,
    /// and the same one the spine's conversation rows wear.
    static let cardCornerRadius: CGFloat = 13
    static let cardPaddingHorizontal: CGFloat = 14
    static let cardPaddingVertical: CGFloat = 11
    /// Between two cards in the same section.
    static let cardGap: CGFloat = 8
    /// Between a card's glyph and its content, and between the two lines inside it.
    static let cardGlyphGap: CGFloat = 10
    static let cardLineGap: CGFloat = 3
    static let checkGlyphSize: CGFloat = 14

    /// How much of an app's reading is shown before it is folded away, and the control that unfolds
    /// it. The reference's own threshold — a paragraph under it is not worth a disclosure.
    static let appResultCollapsedLength = 200
    static let disclosureGlyphSize: CGFloat = 10

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

    /// Which pane the reader asked for. False is the summary, which is where a conversation opens —
    /// see `ActivityDetailPane`.
    @State private var showsTranscript: Bool

    /// The lines an action item claimed to come from, while its `Source` control is what put the
    /// transcript on screen. Cleared on any other route into the transcript, so a highlight is
    /// always the answer to a question the reader just asked.
    @State private var focusedSegmentIDs: Set<String>

    /// Both pane parameters are empty in the app — a conversation opens on its summary with nothing
    /// marked — and settable because the states they describe are reached only by a press, which is
    /// the one thing a still frame cannot make. The render harness is their only caller.
    ///
    /// - Parameter showsTranscript: which pane the screen opens on.
    /// - Parameter focusedSegmentIDs: the lines an action item pointed at.
    init(
        request: ActivityDetailRequest,
        model: ActivityDetailModel,
        onBack: @escaping () -> Void,
        onOpen: @escaping (ActivityDetailRequest) -> Void = { _ in },
        showsTranscript: Bool = false,
        focusedSegmentIDs: Set<String> = []
    ) {
        self.request = request
        _model = ObservedObject(wrappedValue: model)
        self.onBack = onBack
        self.onOpen = onOpen
        _showsTranscript = State(initialValue: showsTranscript)
        _focusedSegmentIDs = State(initialValue: focusedSegmentIDs)
    }

    var body: some View {
        Group {
            switch request.subject {
            case .conversation(let conversation): conversationScreen(conversation)
            case .memory, .task: contextScreen
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .accessibilityIdentifier("activity-detail")
        // The surface reuses this view across requests, so a transcript left open on one
        // conversation would be the pane the next one opened in.
        .onChange(of: request.id) { _, _ in
            showsTranscript = false
            focusedSegmentIDs = []
        }
    }

    // MARK: The two panes of a conversation

    /// A conversation is a summary standing in front of a recording, and it is drawn in that order.
    @ViewBuilder
    private func conversationScreen(_ conversation: ActivityConversation) -> some View {
        let isLocal = conversation.source == .local
        VStack(alignment: .leading, spacing: 0) {
            switch ActivityDetailPane.resolve(isLocal: isLocal, transcriptOpen: showsTranscript) {
            case .summary:
                header(showsTranscriptControl: true)
                rule
                page { summarySections(conversation) }
            case .transcript where isLocal:
                // No pane to go back to, so the ordinary header stays: this *is* the local
                // conversation's only screen, and the way out of it is Activity.
                header(showsTranscriptControl: false)
                rule
                page { localTranscriptSections(conversation) }
            case .transcript:
                transcriptHeader
                rule
                transcriptPane
            }
        }
    }

    /// A memory or a task, which has no second pane: it is whole in the request already.
    private var contextScreen: some View {
        VStack(alignment: .leading, spacing: 0) {
            header(showsTranscriptControl: false)
            rule
            page { contextSection }
        }
    }

    private var rule: some View {
        Rectangle().fill(Ink.separator).frame(height: 1)
    }

    /// The scrolling body every pane but the account transcript uses.
    private func page<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: ActivityDetailMetrics.sectionGap) {
                content()
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, ActivityDetailMetrics.horizontalPadding)
            .padding(.top, ActivityDetailMetrics.bodyTopPadding)
            .padding(.bottom, ActivityDetailMetrics.bodyBottomPadding)
        }
    }

    // MARK: Header

    private func header(showsTranscriptControl: Bool) -> some View {
        HStack(alignment: .top, spacing: ActivityDetailMetrics.headerGap) {
            ActivityDetailBackChip(
                glyph: "chevron.left", label: "Activity", help: "Back to Activity (Escape)",
                identifier: "activity-detail-back", action: onBack)
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
            Spacer(minLength: ActivityDetailMetrics.chipGap)
            headerControls(showsTranscriptControl: showsTranscriptControl)
        }
        .padding(.horizontal, ActivityDetailMetrics.horizontalPadding)
        .padding(.top, ActivityDetailMetrics.headerTopPadding)
        .padding(.bottom, ActivityDetailMetrics.headerBottomPadding)
    }

    /// The reference's trailing header: the status badge when there is one, then the control that
    /// reaches the other pane. Its editing toolbar is not ported — nothing on this surface writes.
    @ViewBuilder
    private func headerControls(showsTranscriptControl: Bool) -> some View {
        HStack(spacing: ActivityDetailMetrics.chipGap) {
            if let status = loadedBody?.status {
                ActivityDetailChip(
                    glyph: status.isWorking ? "clock" : "exclamationmark.triangle",
                    label: status.label,
                    tint: status.isWorking ? Ink.secondary : Ink.errorRed)
            }
            if showsTranscriptControl {
                ActivityDetailBackChip(
                    glyph: "text.quote", label: ActivityDetailCopy.viewTranscript,
                    help: "Show the transcript", identifier: "activity-detail-view-transcript",
                    action: { openTranscript(focusing: []) })
            }
        }
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

    /// When it happened, and the one chip that qualifies it.
    private var metaLine: some View {
        HStack(spacing: ActivityDetailMetrics.chipGap) {
            Text(timing)
                .inkStyle(.statusLabel, color: Ink.secondary)
                .lineLimit(1)
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
    /// A conversation states the day and the window it ran over — the reference's
    /// `MMM d, yyyy from h:mm a to h:mm a`, in this app's own day vocabulary so that "Today" and
    /// "Yesterday" read the way they do everywhere else on the spine. **How long it took is not
    /// here**: the reference makes that a metadata chip in the body and so does this screen, and a
    /// duration stated in both places is the same fact competing with itself.
    ///
    /// A memory or a task states the day and the minute, which is precisely what the row could not:
    /// a row prints the time and leaves the day to the sticky header above it, and there is no
    /// header above this.
    private var timing: String {
        switch request.subject {
        case .conversation(let conversation):
            return ActivityFormat.day(conversation.startedAt) + " · "
                + ActivityFormat.window(from: conversation.startedAt, duration: conversation.duration)
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

    // MARK: The summary pane

    /// The reference's `summaryContent`, in the reference's order, with the two sections that need
    /// an app catalog dropped.
    @ViewBuilder
    private func summarySections(_ conversation: ActivityConversation) -> some View {
        switch model.state {
        case .reading:
            ActivityDetailPlaceholder(
                glyph: nil, headline: "Reading this conversation…", detail: nil)
        case .unread(let sentence):
            ActivityDetailPlaceholder(
                glyph: "exclamationmark.triangle", headline: sentence,
                detail: nil, retry: { model.retry() })
        case .read(let body):
            // Ahead of everything, because it is the reason the rest of the page is thin.
            if let status = body.status { processingNotice(status) }
            if let overview = body.overview {
                section(glyph: "text.alignleft", title: ActivityDetailCopy.summaryHeading) {
                    Text(overview)
                        .inkStyle(.prose, color: Ink.primary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: ActivityDetailMetrics.proseMaxWidth, alignment: .leading)
                        .textSelection(.enabled)
                }
            }
            metadataRow(body, conversation: conversation)
            if !body.appResults.isEmpty {
                section(glyph: "square.grid.2x2", title: ActivityDetailCopy.appInsightsHeading) {
                    VStack(alignment: .leading, spacing: ActivityDetailMetrics.cardGap) {
                        ForEach(body.appResults) { ActivityAppResultCard(result: $0) }
                    }
                }
            }
            if !body.actionItems.isEmpty { actionItemsSection(body.actionItems) }
            // The reference never reaches this: its page always carries the "Try with Apps" rail, so
            // it is never three chips and nothing. Ours can be, and a bare page that does not say
            // why is a page the reader reads as broken.
            if !body.hasSummary && body.status == nil {
                Text(ActivityDetailCopy.noSummary)
                    .inkStyle(.statusLabel, color: Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: ActivityDetailMetrics.proseMaxWidth, alignment: .leading)
            }
        }
    }

    /// The reference's metadata chips: where it was captured, how long it ran, what it was about.
    ///
    /// A chip is dropped rather than drawn empty — a source this client has no word for, a category
    /// the backend itself called `other`, a conversation with no width. The reference prints
    /// "Unknown" and "0s" for the first and the third; a chip that says nothing has still taken a
    /// place in the row and made the reader look at it.
    private func metadataRow(
        _ body: ActivityConversationBody, conversation: ActivityConversation
    ) -> some View {
        HStack(spacing: ActivityDetailMetrics.chipGap) {
            if let source = body.source {
                ActivityDetailChip(glyph: "dot.radiowaves.left.and.right", label: source)
            }
            if conversation.duration >= 1 {
                ActivityDetailChip(
                    glyph: "hourglass", label: ActivityFormat.duration(conversation.duration))
            }
            if let category = body.category {
                ActivityDetailChip(glyph: "tag", label: category.capitalized)
            }
            Spacer(minLength: 0)
        }
    }

    /// Why there is no summary yet, or no summary coming.
    ///
    /// The reference overlays this while it *polls* the account every two seconds until enrichment
    /// finishes. This screen reads once, so the spinner is a statement rather than a countdown and
    /// the reader is given the same `Try again` every other unfinished state here offers. Polling a
    /// rate-limited account from a panel that opens on a keystroke is the thing `ActivityDetailCopy`
    /// exists to avoid.
    @ViewBuilder
    private func processingNotice(_ status: ActivityConversationStatus) -> some View {
        ActivityDetailNotice(
            glyph: status.isWorking ? nil : "exclamationmark.triangle",
            headline: status.isWorking
                ? ActivityDetailCopy.processing : ActivityDetailCopy.processingFailed,
            detail: status.isWorking
                ? ActivityDetailCopy.processingDetail : ActivityDetailCopy.processingFailedDetail,
            action: status.isWorking ? { model.retry() } : nil)
    }

    private func actionItemsSection(_ items: [ActivityActionItem]) -> some View {
        section(
            glyph: "checklist", title: ActivityDetailCopy.actionItemsHeading, count: items.count
        ) {
            VStack(alignment: .leading, spacing: ActivityDetailMetrics.cardGap) {
                ForEach(items) { item in
                    ActivityActionItemRow(
                        item: item,
                        onOpenSource: { openTranscript(focusing: item.sourceSegmentIDs) })
                }
            }
        }
    }

    /// A labelled block. One shape for every section on the page, so the ladder cannot drift.
    private func section<Content: View>(
        glyph: String, title: String, count: Int? = nil, @ViewBuilder _ content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: ActivityDetailMetrics.sectionLabelGap) {
            ActivityDetailSectionLabel(glyph: glyph, title: title, count: count)
            content()
        }
    }

    // MARK: The transcript pane

    /// The reference's drawer header — the word, the count, and the way out — with its ✕ replaced by
    /// the leading chip this panel navigates with everywhere else.
    ///
    /// **Escape is still one level up, not one pane back.** It is consumed by `ActivityDetailEscape`
    /// on behalf of the whole detail (the panel takes key 53 before this view hierarchy can see it),
    /// so from here it returns to Activity rather than to the summary. The chip is the pane's own
    /// way back and is the reason that is survivable.
    private var transcriptHeader: some View {
        HStack(spacing: ActivityDetailMetrics.headerGap) {
            ActivityDetailBackChip(
                glyph: "chevron.left", label: ActivityDetailCopy.backToSummary,
                help: "Back to the summary", identifier: "activity-detail-back-to-summary",
                action: {
                    showsTranscript = false
                    focusedSegmentIDs = []
                })
            ActivityDetailSectionLabel(
                glyph: "text.quote", title: ActivityDetailCopy.transcriptHeading,
                count: loadedBody?.lines.count)
            Spacer(minLength: ActivityDetailMetrics.chipGap)
            if let lines = loadedBody?.lines, !lines.isEmpty {
                ActivityDetailBackChip(
                    glyph: "doc.on.doc", label: "Copy", help: "Copy the transcript",
                    identifier: "activity-detail-copy-transcript",
                    action: { copyTranscript(lines) })
            }
        }
        .padding(.horizontal, ActivityDetailMetrics.horizontalPadding)
        .padding(.top, ActivityDetailMetrics.headerTopPadding)
        .padding(.bottom, ActivityDetailMetrics.headerBottomPadding)
    }

    /// The account transcript: the only thing on its pane, so the lines own the scroll view and the
    /// reader can be taken to one of them.
    @ViewBuilder
    private var transcriptPane: some View {
        switch model.state {
        case .read(let body) where !body.lines.isEmpty:
            ScrollViewReader { proxy in
                ScrollView {
                    transcriptLines(body.lines)
                        .padding(.horizontal, ActivityDetailMetrics.horizontalPadding)
                        .padding(.top, ActivityDetailMetrics.bodyTopPadding)
                        .padding(.bottom, ActivityDetailMetrics.bodyBottomPadding)
                }
                .onAppear { scrollToFocus(using: proxy) }
                .onChange(of: focusedSegmentIDs) { _, _ in scrollToFocus(using: proxy) }
            }
        default:
            page { transcriptPlaceholder }
        }
    }

    /// A local conversation's only screen: why there is no summary, the two facts about it that are
    /// knowable, and then the lines.
    @ViewBuilder
    private func localTranscriptSections(_ conversation: ActivityConversation) -> some View {
        Text(ActivityDetailCopy.localOnly)
            .inkStyle(.statusLabel, color: Ink.secondary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: ActivityDetailMetrics.proseMaxWidth, alignment: .leading)
        if let body = loadedBody {
            metadataRow(body, conversation: conversation)
        }
        section(
            glyph: "text.quote", title: ActivityDetailCopy.transcriptHeading,
            count: loadedBody?.lines.count
        ) {
            if let lines = loadedBody?.lines, !lines.isEmpty {
                transcriptLines(lines)
            } else {
                transcriptPlaceholder
            }
        }
    }

    /// `LazyVStack` rather than `VStack`: a long call is hundreds of lines.
    private func transcriptLines(_ lines: [ActivityTranscriptLine]) -> some View {
        LazyVStack(alignment: .leading, spacing: ActivityDetailMetrics.lineGap) {
            ForEach(lines) { line in
                ActivityTranscriptRow(line: line, isFocused: focusedSegmentIDs.contains(line.id))
                    .id(line.id)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Everything the transcript can be other than a list of lines.
    @ViewBuilder
    private var transcriptPlaceholder: some View {
        switch model.state {
        case .reading:
            ActivityDetailPlaceholder(
                glyph: nil, headline: "Reading this conversation…", detail: nil)
        case .unread(let sentence):
            ActivityDetailPlaceholder(
                glyph: "exclamationmark.triangle", headline: sentence,
                detail: nil, retry: { model.retry() })
        case .read:
            ActivityDetailPlaceholder(
                glyph: "text.quote",
                headline: isLocal
                    ? ActivityDetailCopy.noLocalTranscript : ActivityDetailCopy.noTranscript,
                detail: isLocal ? nil : ActivityDetailCopy.noTranscriptDetail)
        }
    }

    private var isLocal: Bool {
        guard case .conversation(let conversation) = request.subject else { return false }
        return conversation.source == .local
    }

    private func openTranscript(focusing ids: [String]) {
        focusedSegmentIDs = Set(ids)
        showsTranscript = true
    }

    /// Takes the reader to the first line an action item pointed at.
    ///
    /// Deferred to the next turn of the main queue because the pane has only just been swapped in:
    /// a `scrollTo` issued while the `ScrollView` is still laying out its first frame lands nowhere.
    private func scrollToFocus(using proxy: ScrollViewProxy) {
        guard let first = loadedBody?.lines.first(where: { focusedSegmentIDs.contains($0.id) })
        else { return }
        DispatchQueue.main.async {
            withAnimation(InkReduceMotion.animation(.easeInOut(duration: InkMotion.settle))) {
                proxy.scrollTo(first.id, anchor: .center)
            }
        }
    }

    /// The reference's own transcript format, `[Speaker]: text`, blank line between turns.
    private func copyTranscript(_ lines: [ActivityTranscriptLine]) {
        let text = lines.map { "[\($0.speaker)]: \($0.text)" }.joined(separator: "\n\n")
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
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

// MARK: - The chips that navigate

/// The panel's one control shape: a glyph, a word, and the pill every other control here wears.
///
/// One view for `‹ Activity`, `‹ Summary`, `View Transcript` and `Copy`, because they are one
/// control with four labels — and because a second copy of this pill is a second opinion about what
/// a control on this surface looks like. The leading chip names its *destination* rather than saying
/// "Back": the panel has several bodies and the reader may have arrived from any of them.
private struct ActivityDetailBackChip: View {
    let glyph: String
    let label: String
    let help: String
    let identifier: String
    let action: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: ActivityDetailMetrics.backChipGap) {
                Image(systemName: glyph)
                    .font(
                        .system(size: ActivityDetailMetrics.backChipGlyphSize, weight: .semibold))
                Text(label)
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
        .help(help)
        .accessibilityLabel(Text(label))
        .accessibilityIdentifier(identifier)
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

/// A qualifying word: the account's category, where it was captured, how long it ran, a task's
/// state, a conversation the account has not finished with.
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

/// A statement about the whole page, sitting above it: the account is still working, or it gave up.
///
/// A card and not a placeholder, because the page around it is not empty — the reference makes the
/// same distinction, overlaying this above details that may already have arrived rather than
/// replacing them.
private struct ActivityDetailNotice: View {
    /// Nil while the account is working, where the spinner is the glyph.
    let glyph: String?
    let headline: String
    let detail: String
    var action: (() -> Void)?

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: ActivityDetailMetrics.cardCornerRadius, style: .continuous)
    }

    var body: some View {
        HStack(alignment: .top, spacing: ActivityDetailMetrics.cardGlyphGap) {
            if let glyph {
                Image(systemName: glyph)
                    .font(.system(size: ActivityDetailMetrics.checkGlyphSize, weight: .regular))
                    .foregroundStyle(Ink.errorRed)
            } else {
                ProgressView().controlSize(.small)
            }
            VStack(alignment: .leading, spacing: ActivityDetailMetrics.cardLineGap) {
                Text(headline).inkStyle(.rowCopy, color: Ink.primary)
                Text(detail)
                    .inkStyle(.statusLabel, color: Ink.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: ActivityDetailMetrics.chipGap)
            if let action {
                ActivityDetailBackChip(
                    glyph: "arrow.clockwise", label: "Try again", help: "Read this again",
                    identifier: "activity-detail-retry-processing", action: action)
            }
        }
        .padding(.horizontal, ActivityDetailMetrics.cardPaddingHorizontal)
        .padding(.vertical, ActivityDetailMetrics.cardPaddingVertical)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(shape.fill(Ink.rowFill))
        .overlay(shape.strokeBorder(Ink.separator, lineWidth: 1))
        .accessibilityIdentifier("activity-detail-notice")
    }
}

/// One thing somebody committed to, and the way to the lines it was drawn from.
///
/// The control is labelled `Source` only when the account actually recorded which segments it read;
/// otherwise it is plainly `Transcript`, because a "source" that lands the reader at the top of the
/// whole recording is a promise the record cannot keep. That distinction is the reference's.
private struct ActivityActionItemRow: View {
    let item: ActivityActionItem
    let onOpenSource: () -> Void

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: ActivityDetailMetrics.cardCornerRadius, style: .continuous)
    }

    var body: some View {
        HStack(alignment: .top, spacing: ActivityDetailMetrics.cardGlyphGap) {
            Image(systemName: item.isCompleted ? "checkmark.circle.fill" : "circle")
                .font(.system(size: ActivityDetailMetrics.checkGlyphSize, weight: .regular))
                .foregroundStyle(item.isCompleted ? Ink.listeningGreen : Ink.secondary)
            Text(item.text)
                .inkStyle(.rowCopy, color: item.isCompleted ? Ink.secondary : Ink.primary)
                .strikethrough(item.isCompleted, color: Ink.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: ActivityDetailMetrics.proseMaxWidth, alignment: .leading)
                .textSelection(.enabled)
            Spacer(minLength: ActivityDetailMetrics.chipGap)
            Button(action: onOpenSource) {
                HStack(spacing: ActivityDetailMetrics.backChipGap) {
                    Image(systemName: "text.quote")
                        .font(.system(size: ActivityDetailMetrics.chipGlyphSize, weight: .medium))
                    Text(
                        item.sourceSegmentIDs.isEmpty
                            ? ActivityDetailCopy.actionItemTranscript
                            : ActivityDetailCopy.actionItemSource
                    )
                    .inkStyle(.statusLabel)
                    .fixedSize()
                }
                .foregroundStyle(Ink.secondary)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("Open the transcript")
            .accessibilityIdentifier("activity-detail-action-item-source")
        }
        .padding(.horizontal, ActivityDetailMetrics.cardPaddingHorizontal)
        .padding(.vertical, ActivityDetailMetrics.cardPaddingVertical)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(shape.fill(Ink.rowFill))
        .overlay(shape.strokeBorder(Ink.separator, lineWidth: 1))
    }
}

/// What one app made of the conversation, folded when it runs long.
///
/// The reference's card carries the app's icon, name and author above the prose and a "Generated by"
/// footer under it; all of that comes from a catalog this app has no way to load, and its own
/// catalog-less branch degrades to the literal word "App". So the card is the prose, and the
/// section label above it says whose kind of thing it is.
private struct ActivityAppResultCard: View {
    let result: ActivityAppResult

    @State private var isExpanded = false

    private var isFoldable: Bool {
        result.content.count >= ActivityDetailMetrics.appResultCollapsedLength
    }

    private var shown: String {
        guard isFoldable, !isExpanded else { return result.content }
        return String(result.content.prefix(ActivityDetailMetrics.appResultCollapsedLength)) + "…"
    }

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: ActivityDetailMetrics.cardCornerRadius, style: .continuous)
    }

    var body: some View {
        HStack(alignment: .top, spacing: ActivityDetailMetrics.cardGlyphGap) {
            Text(shown)
                .inkStyle(.prose, color: Ink.primary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: ActivityDetailMetrics.proseMaxWidth, alignment: .leading)
                .textSelection(.enabled)
            Spacer(minLength: 0)
            if isFoldable {
                Button(action: { isExpanded.toggle() }) {
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .font(
                            .system(
                                size: ActivityDetailMetrics.disclosureGlyphSize, weight: .semibold)
                        )
                        .foregroundStyle(Ink.secondary)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .help(isExpanded ? "Show less" : "Show all of it")
                .accessibilityIdentifier("activity-detail-app-result-disclosure")
            }
        }
        .padding(.horizontal, ActivityDetailMetrics.cardPaddingHorizontal)
        .padding(.vertical, ActivityDetailMetrics.cardPaddingVertical)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(shape.fill(Ink.rowFill))
        .overlay(shape.strokeBorder(Ink.separator, lineWidth: 1))
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
///
/// `isFocused` marks a line an action item claimed to come from. An outline rather than a fill,
/// because the fills are already spoken for: a `you` bubble is `rowFillHover`, and a mark that
/// happened to match it would be invisible on exactly half the lines.
struct ActivityTranscriptRow: View {
    let line: ActivityTranscriptLine
    var isFocused = false

    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: ActivityDetailMetrics.focusCornerRadius, style: .continuous)
    }

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
        .padding(.horizontal, ActivityDetailMetrics.focusInsetHorizontal)
        .padding(.vertical, ActivityDetailMetrics.focusInsetVertical)
        .background(shape.fill(isFocused ? Ink.wash : Color.clear))
        .overlay(shape.strokeBorder(isFocused ? Ink.hairline : Color.clear, lineWidth: 1))
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
                        source: "Desktop",
                        actionItems: [
                            ActivityActionItem(
                                id: "a1", text: "Send the migration plan to Priya",
                                isCompleted: false, sourceSegmentIDs: ["2"])
                        ],
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
