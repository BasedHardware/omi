import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// The summary at the top of the page: its first two or three sentences, "More" for the rest.
/// A failed summary offers a retry. The summary can be edited in place (the backend's
/// `PATCH v1/conversations/{id}/summary`): the new text shows at once, the old one comes back when
/// the backend refuses, and the editor stays open with the draft and what went wrong.
struct ConversationSummaryView: View {
    let store: ConversationDetailStore
    let conversation: Conversation
    let onRetry: () -> Void
    /// The edited summary was stored; the screen shows its "Summary saved" toast.
    var onSaved: () -> Void = {}
    @State private var expanded = false
    @State private var editing = false
    @State private var draft = ""
    @State private var saving = false
    /// Why the last save did not go through; the editor stays open and says so.
    @State private var failed: SummaryEditFailure?
    @FocusState private var focused: Bool

    /// The backend's own ceiling on the summary (`PATCH` refuses more).
    private static let limit = 10_000

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.md) {
            // Processing shows in the strip under the title (ProcessingStrip).
            if !store.isReprocessing, conversation.status != .processing, conversation.summaryFailed {
                failedCard
            }
            let summary = store.detail?.summary ?? conversation.overview
            if editing {
                editor
            } else if summary.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Text(L("nativeNoSummary")).font(DS.Typography.body).foregroundStyle(DS.Palette.inkSecondary)
            } else {
                text(summary)
            }
        }
    }

    /// Editing waits until Omi is done with this conversation: during processing or a reprocess the
    /// summary on screen is about to be replaced.
    private var canEdit: Bool {
        !store.isReprocessing && conversation.status != .processing && !conversation.summaryFailed
            && store.canEditSummary
    }

    @ViewBuilder
    private func text(_ summary: String) -> some View {
        // The backend's own gist when it kept one, else the summary's first sentences.
        let lead = store.detail?.gist.map { (text: $0, isShortened: $0 != summary) } ?? ConversationDigest.lead(of: summary)
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            if expanded || !lead.isShortened {
                MarkdownBlocks(summary).foregroundStyle(DS.Palette.ink).lineSpacing(3)
            } else {
                Text(lead.text)
                    .font(DS.Typography.body)
                    .foregroundStyle(DS.Palette.ink)
                    .lineSpacing(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if lead.isShortened {
                Button {
                    withAnimation(DS.Motion.standard) { expanded.toggle() }
                } label: {
                    Text(expanded ? L("nativeLess") : L("nativeMore"))
                        .font(DS.Typography.callout.weight(.medium))
                        .foregroundStyle(DS.Palette.inkSecondary)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("summary.more")
            }
            if canEdit {
                HStack {
                    Spacer(minLength: 0)
                    Button { startEditing(summary) } label: {
                        Label(L("nativeEditSummary"), systemImage: "square.and.pencil")
                    }
                    .buttonStyle(.omiPillSubtle)
                    .accessibilityIdentifier("summary.edit")
                }
            }
        }
        .textSelection(.enabled)
    }

    // MARK: Editing in place

    private var editor: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            TextEditor(text: $draft)
                .font(DS.Typography.body)
                .foregroundStyle(DS.Palette.ink)
                .scrollContentBackground(.hidden)
                .frame(minHeight: 150)
                .padding(DS.Spacing.sm)
                .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: DS.Radius.md, style: .continuous))
                .focused($focused)
                .disabled(saving)
                .accessibilityIdentifier("summary.editor")
                .onChange(of: draft) { _, text in
                    if text.count > Self.limit { draft = String(text.prefix(Self.limit)) }
                }
            if let failed {
                Label(Self.message(failed), systemImage: "exclamationmark.triangle")
                    .font(DS.Typography.caption)
                    .foregroundStyle(DS.Palette.live)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("summary.edit.failure")
            }
            HStack(spacing: DS.Spacing.sm) {
                Text("\(draft.count)/\(Self.limit)")
                    .font(DS.Typography.caption)
                    .foregroundStyle(DS.Palette.inkTertiary)
                    .accessibilityHidden(true)
                Spacer(minLength: 0)
                if saving {
                    ProgressView().controlSize(.small)
                } else {
                    Button(L("cancel")) { stopEditing() }.buttonStyle(.omiPillSubtle)
                    Button(L("save")) { Task { await save() } }
                        .buttonStyle(.omiPill)
                        .disabled(draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        .accessibilityIdentifier("summary.save")
                }
            }
        }
        // The keyboard comes up on the text, the way tapping into any editor does.
        .onAppear { focused = true }
    }

    private func startEditing(_ summary: String) {
        DSHaptics.tap(.medium)
        draft = summary
        failed = nil
        withAnimation(DS.Motion.standard) { editing = true }
    }

    private func stopEditing() {
        focused = false
        withAnimation(DS.Motion.standard) { editing = false }
        draft = ""
        failed = nil
    }

    private func save() async {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !saving else { return }
        saving = true
        let outcome = await store.editSummary(text)
        saving = false
        switch outcome {
        case .saved:
            DSHaptics.success()
            stopEditing()
            onSaved()
        case .unchanged:
            // Nothing to send (the text is what the summary already shows).
            stopEditing()
        case .failed(let reason):
            // The draft stays; the summary behind it is back to the old text.
            failed = reason
        }
    }

    /// What went wrong, in words.
    static func message(_ failure: SummaryEditFailure) -> String {
        switch failure {
        case .appResultGone: L("nativeSummarySaveAppResultGone")
        case .appResultAmbiguous: L("nativeSummarySaveAppResultAmbiguous")
        case .conversationGone: L("nativeSummarySaveConversationGone")
        case .offline: L("nativeSummarySaveOffline")
        case .signedOut: L("nativeSummarySaveSignedOut")
        case .refused(nil): L("nativeSummarySaveRefused")
        case .refused(let status?): L("nativeSummarySaveRefusedStatus", "\(status)")
        }
    }

    private var failedCard: some View {
        HStack(spacing: DS.Spacing.md) {
            Image(systemName: "exclamationmark.triangle").foregroundStyle(DS.Palette.warning)
            Text(L("nativeSummaryFailed")).font(DS.Typography.callout.weight(.medium))
            Spacer(minLength: 0)
            Button(L("retry"), action: onRetry).buttonStyle(.omiPillSubtle)
        }
        .omiCard(padding: DS.Spacing.md)
    }
}

/// The page's three ways to use a conversation: ask about it, check it in the transcript, send it
/// to your own AI.
struct DetailActions: View {
    let onAsk: () -> Void
    let onCheck: () -> Void
    let onSend: () -> Void

    var body: some View {
        // One row; stacked when large text does not fit.
        ViewThatFits(in: .horizontal) {
            HStack(spacing: DS.Spacing.sm) { actions }
            VStack(alignment: .leading, spacing: DS.Spacing.sm) { actions }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private var actions: some View {
        action(L("nativeAsk"), "bubble.left", id: "ask", onAsk)
        action(L("nativeCheck"), "text.magnifyingglass", id: "check", onCheck)
        action(L("nativeSendToMyAI"), "square.and.arrow.up", id: "send", onSend)
    }

    private func action(_ title: String, _ symbol: String, id: String, _ perform: @escaping () -> Void) -> some View {
        Button(action: perform) {
            HStack(spacing: 6) {
                Image(systemName: symbol).font(.system(size: 14, weight: .regular)).accessibilityHidden(true)
                Text(title).lineLimit(1)
            }
            .font(.subheadline.weight(.medium))
            .foregroundStyle(DS.Palette.ink)
            .padding(.horizontal, 14)
            .frame(minHeight: 38)
            .overlay { Capsule().strokeBorder(DS.Palette.fill, lineWidth: 1) }
            .contentShape(Capsule())
        }
        .buttonStyle(.hapticTap)
        .accessibilityIdentifier("conversation.action.\(id)")
    }
}

/// Everything beyond the summary and action items, behind one "More details": what was decided
/// and found (key points, events, other apps' summaries), who took part, the linked event, photos,
/// what was on screen, and "Was this helpful?".
struct MoreDetailsSection: View {
    let store: ConversationDetailStore
    let extras: DetailExtras
    let conversation: Conversation
    @State private var expanded = DebugLaunch.flag("omiMoreDetails")
    @Environment(TasksStore.self) private var tasks
    @Environment(ConversationsStore.self) private var conversations

    var body: some View {
        if let detail = store.detail {
            VStack(alignment: .leading, spacing: DS.Spacing.xl) {
                Button {
                    DSHaptics.selection()
                    withAnimation(DS.Motion.standard) { expanded.toggle() }
                } label: {
                    HStack(spacing: DS.Spacing.xs) {
                        Text(L("nativeMoreDetails"))
                        Image(systemName: "chevron.down")
                            .font(.system(size: 12, weight: .regular))
                            .rotationEffect(.degrees(expanded ? 180 : 0))
                    }
                    .font(DS.Typography.sectionLabel)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(expanded ? .isSelected : [])
                .accessibilityIdentifier("conversation.moreDetails")
                if expanded {
                    VStack(alignment: .leading, spacing: DS.Spacing.xl) {
                        ConversationInsightsView(detail: detail, onEvent: { extras.addingEvent = $0 })
                        SummaryExtrasSection(store: store, extras: extras)
                        ParticipantsRow(store: store) { extras.showsEvent = true }
                        othersTasks
                        ConversationPhotosGrid(store: store)
                    }
                    .transition(.opacity)
                }
            }
            // Loads what the extras need (feedback, screenshots) whether or not they show yet.
            .modifier(SummaryExtrasLoader(store: store, extras: extras))
        }
    }

    @ViewBuilder
    private var othersTasks: some View {
        let others = tasks.othersTasks(forConversation: conversation.id)
        if !others.isEmpty {
            DetailGroup(L("nativeWaitingOnOthers")) {
                ForEach(others) { task in
                    TaskRow(task, onToggle: { Task { await tasks.setCompleted(task.id, !task.isCompleted) } })
                }
            }
        }
    }
}

/// A labeled group inside "More details": small gray label, rows on the page.
struct DetailGroup<Content: View>: View {
    let title: String
    let content: Content

    init(_ title: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            Text(title)
                .font(DS.Typography.sectionLabel)
                .foregroundStyle(DS.Palette.inkSecondary)
                .accessibilityAddTraits(.isHeader)
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Key points, events Omi found, and what the user's other apps wrote.
struct ConversationInsightsView: View {
    let detail: ConversationDetail
    /// A found event was tapped (its index): the screen offers to add it to the calendar.
    let onEvent: (Int) -> Void

    var body: some View {
        if !detail.keyPoints.isEmpty {
            DetailGroup(L("nativeKeyPoints")) {
                ForEach(detail.keyPoints, id: \.self) { point in
                    HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.sm) {
                        Text(verbatim: "•").foregroundStyle(DS.Palette.inkSecondary)
                        Text(LocalizedStringKey(point)).font(DS.Typography.body).foregroundStyle(DS.Palette.ink)
                    }
                }
            }
        }
        let shown = detail.events.indices.filter { !detail.events[$0].title.isEmpty }
        if !shown.isEmpty {
            DetailGroup(L("nativeEvents")) {
                ForEach(shown, id: \.self) { index in
                    Button { onEvent(index) } label: { eventRow(detail.events[index]) }
                        .buttonStyle(.plain)
                        .disabled(detail.events[index].isCreated)
                }
            }
        }
        ForEach(Array(detail.otherSummaries.enumerated()), id: \.offset) { _, other in
            DetailGroup(L("nativeFromYourApps")) {
                MarkdownBlocks(other.content).foregroundStyle(DS.Palette.ink)
            }
        }
    }

    /// One found event; tapping it adds it to the calendar (a check once it is there).
    private func eventRow(_ event: ConversationDetail.Event) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.md) {
            Image(systemName: "calendar").foregroundStyle(DS.Palette.inkSecondary).frame(width: 22).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(event.title).font(DS.Typography.cardTitle).foregroundStyle(DS.Palette.ink)
                if let start = event.start {
                    Text(start.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day().hour().minute()))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkSecondary)
                }
                if !event.description.isEmpty {
                    Text(event.description).font(DS.Typography.caption).foregroundStyle(DS.Palette.inkSecondary)
                }
            }
            Spacer(minLength: 0)
            Image(systemName: event.isCreated ? "checkmark" : "plus")
                .font(.system(size: 15, weight: .regular))
                .foregroundStyle(event.isCreated ? DS.Palette.success : DS.Palette.inkSecondary)
                .accessibilityLabel(event.isCreated ? L("nativeAddedToCalendar") : L("nativeAddToCalendar"))
        }
        .multilineTextAlignment(.leading)
        .padding(.vertical, DS.Spacing.xs)
        .contentShape(Rectangle())
    }
}
