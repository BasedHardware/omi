import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// Omi's conversation page: title and date, then Summary | Transcript side by side (swipe or tap
/// the labels). The summary page leads with what came out of it (VISION.md, Phase A): the summary
/// in a few sentences, the action items, and Ask / Check / Send to my AI; everything else waits
/// behind "More details". The share button and the "…" menu hold every action
/// (`ConversationDetailMenu.swift`).
public struct ConversationDetailScreen: View {
    enum Page: Hashable { case summary, transcript }

    @State var store: ConversationDetailStore
    @Environment(TasksStore.self) var tasks
    @Environment(ConversationsStore.self) var conversations
    @Environment(AgentStore.self) var agent
    @Environment(ChatStore.self) var chat
    /// Conversation developer tools (Copy ID).
    @Environment(DeveloperStore.self) var developer
    @Environment(\.dismiss) var dismiss
    @State var renaming = false
    @State var newTitle = ""
    @State var page = DebugLaunch.string("omiConversationPage") == "transcript" ? Page.transcript : Page.summary
    /// 0 on Summary, 1 on Transcript, in between while swiping (drives the underline).
    @State private var pageProgress: CGFloat = DebugLaunch.string("omiConversationPage") == "transcript" ? 1 : 0
    /// Where the tab labels sit, for the underline.
    @State private var tabFrames: [Page: CGRect] = [:]
    @State var moving = false
    @State var sharing: ShareRequest?
    @State var confirmsShareLink = false
    /// A short confirmation ("Summary copied"), shown for a moment.
    @State var notice: String?
    @State private var query = ""
    @State private var cursor = 0
    /// The transcript's search field is open (magnifier above the page, or the "…" menu).
    @State var searchesTranscript = DebugLaunch.flag("omiTranscriptSearch")
    /// Summary template, calendar, recordings, SMS, test prompt (`DetailExtras.swift`).
    @State var extras = DetailExtras()
    let onHandOver: (ActionItem) -> Void
    let onAskOmi: () -> Void

    /// `onAskOmi` opens the chat; the screen has already pointed it at this conversation.
    public init(store: ConversationDetailStore, onHandOver: @escaping (ActionItem) -> Void, onAskOmi: @escaping () -> Void = {}) {
        _store = State(initialValue: store)
        self.onHandOver = onHandOver
        self.onAskOmi = onAskOmi
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: DS.Spacing.md) {
                header
                ProcessingStrip(store: store, conversation: conversation)
                tabs
            }
            .padding(.horizontal, DS.Spacing.gutter)
            // Summary and Transcript side by side in one paging scroll view: swipe between them and
            // the underline follows the finger; each page scrolls vertically on its own.
            ScrollView(.horizontal) {
                LazyHStack(spacing: 0) {
                    summaryPage.containerRelativeFrame(.horizontal).id(Page.summary)
                    transcriptPage.containerRelativeFrame(.horizontal).id(Page.transcript)
                }
                .scrollTargetLayout()
            }
            .scrollTargetBehavior(.paging)
            .scrollPosition(id: pagePosition)
            .scrollIndicators(.hidden)
            .scrollBounceBehavior(.basedOnSize, axes: .horizontal)
            .onScrollGeometryChange(for: CGFloat.self) { geometry in
                geometry.containerSize.width > 0 ? geometry.contentOffset.x / geometry.containerSize.width : 0
            } action: { _, progress in
                pageProgress = min(max(progress, 0), 1)
            }
            .task { await swipeForDebugging() }
        }
        .background(DS.Palette.background)
        // The system bar keeps the edge swipe back (a hidden bar turns it off).
        .navigationBarTitleDisplayMode(.inline)
        .toolbar { toolbarItems }
        .task {
            await store.load()
            conversations.remember(store.conversation)
        }
        // The folder name needs the folders (the screen can open straight from search or a link).
        .task { if conversations.folders.isEmpty { await conversations.loadFolders() } }
        .task { if tasks.phase == .idle { await tasks.load() } }
        .task(id: tasks.tasks.count) { await agent.loadWorkstreams(for: tasks.tasks) }
        .alert(L("renameConversation"), isPresented: $renaming) {
            TextField(L("conversationTitle"), text: $newTitle)
            Button(L("cancel"), role: .cancel) {}
            Button(L("save")) { Task { await conversations.rename(conversation.id, to: newTitle) } }
        }
        .confirmationDialog(L("shareConversationQuestion"), isPresented: $confirmsShareLink, titleVisibility: .visible) {
            Button(L("share")) { Task { await shareLink() } }
        } message: {
            Text(L("anyoneWithLinkCanView"))
        }
        .sheet(isPresented: $moving) { MoveToFolderSheet(ids: [conversation.id]).presentationDetents([.medium, .large]) }
        .sheet(item: $sharing) { request in shareSheet(request) }
        .overlay(alignment: .bottom) {
            if let notice {
                OmiToast(text: notice, systemImage: "checkmark").transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(DS.Motion.standard, value: notice)
        .modifier(
            DetailExtrasPresenter(extras: extras, store: store, conversation: conversation, onHandOver: onHandOver, onAskOmi: onAskOmi)
        )
        .onChange(of: extras.notice) { _, message in if let message { show(message) } }
    }

    /// The list's copy wins, so a rename or a star shows here at once.
    var conversation: Conversation {
        conversations.current(store.conversation)
    }

    /// The transcript paragraph holding the current search match.
    private var matchLine: Int? {
        guard page == .transcript, let detail = store.detail else { return nil }
        let matches = detail.lines(matching: query)
        guard !matches.isEmpty else { return nil }
        return TranscriptView.paragraphID(of: matches[min(cursor, matches.count - 1)], in: detail.transcript)
    }

    /// What came out of it: the summary in a few sentences, the action items, three ways to use
    /// it, and everything else behind "More details".
    private var summaryPage: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: DS.Spacing.xl) {
                    ConversationSummaryView(
                        store: store, conversation: conversation,
                        onRetry: { reprocess() }, onSaved: { show(L("nativeSummarySaved")) }
                    )
                    actionItems
                    DetailActions(
                        onAsk: { askOmi() },
                        onCheck: { withAnimation(DS.Motion.standard) { page = .transcript } },
                        onSend: { sendToMyAI() }
                    )
                    MoreDetailsSection(store: store, extras: extras, conversation: conversation).id(Self.moreDetailsAnchor)
                }
                .padding(.horizontal, DS.Spacing.gutter)
                .padding(.top, DS.Spacing.lg)
                .padding(.bottom, DS.Spacing.section)
            }
            .scrollIndicators(.hidden)
            .background { EdgeSwipeBackFirst() }
            .task {
                // `-omiMoreDetails YES` opens "More details" and scrolls to it (scripted screenshots).
                guard DebugLaunch.flag("omiMoreDetails") else { return }
                try? await Task.sleep(for: .seconds(2.5))
                proxy.scrollTo(Self.moreDetailsAnchor, anchor: .top)
            }
        }
    }

    private static let moreDetailsAnchor = "more-details"

    private var transcriptPage: some View {
        ScrollViewReader { proxy in
            ScrollView {
                TranscriptView(
                    store: store, query: $query, cursor: $cursor, showsSearch: $searchesTranscript, onShareAudio: shareAudio
                )
                .padding(.horizontal, DS.Spacing.gutter)
                .padding(.top, DS.Spacing.lg)
                .padding(.bottom, DS.Spacing.section)
            }
            .scrollIndicators(.hidden)
            .scrollDismissesKeyboard(.immediately)
            .onChange(of: matchLine) { _, line in
                guard let line else { return }
                withAnimation(DS.Motion.standard) { proxy.scrollTo(TranscriptView.anchor(line), anchor: .center) }
            }
        }
    }

    /// The emoji on its own, the title, and one quiet line: when, how long, folder, starred, shared.
    private var header: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.xs) {
            HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.sm) {
                if let emoji = conversation.emoji {
                    Text(emoji).font(.system(size: 22)).accessibilityHidden(true)
                }
                Text(conversation.displayTitle)
                    .font(DS.Typography.title)
                    .foregroundStyle(DS.Palette.ink)
                    .lineLimit(3)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: DS.Spacing.sm) {
                Text(when).lineLimit(1)
                if let folder = conversations.folder(conversation.folderID) {
                    FolderLabel(folder: folder).labelStyle(.titleAndIcon).lineLimit(1)
                }
                if conversation.isStarred {
                    Image(systemName: "star.fill").accessibilityLabel(L("starred"))
                }
                if conversation.visibility != .private {
                    Image(systemName: "globe").accessibilityLabel(L("nativeShared"))
                }
            }
            .font(DS.Typography.caption)
            .foregroundStyle(DS.Palette.inkSecondary)
        }
        .padding(.top, DS.Spacing.xs)
    }

    /// "Wed, Oct 7, 3:18 PM · 38m".
    private var when: String {
        let date = conversation.date.formatted(.dateTime.weekday(.abbreviated).month(.abbreviated).day().hour().minute())
        return conversation.duration.map { "\(date) · \(Formatting.length($0))" } ?? date
    }

    private var tabs: some View {
        HStack(spacing: DS.Spacing.xl) {
            tab(L("summary"), .summary)
            tab(L("transcript"), .transcript)
            Spacer()
            // Search lives with the transcript: a small magnifier, the field only when asked for.
            if page == .transcript, store.detail?.transcript.isEmpty == false {
                Button {
                    DSHaptics.selection()
                    withAnimation(DS.Motion.standard) { searchesTranscript.toggle() }
                } label: {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 15, weight: .regular))
                        .foregroundStyle(searchesTranscript ? DS.Palette.ink : DS.Palette.inkSecondary)
                        .frame(width: 32, height: 24)
                        .padding(.bottom, DS.Spacing.sm)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .transition(.opacity)
                .accessibilityLabel(L("searchTranscriptOrSummary"))
                .accessibilityIdentifier("transcript.search")
            }
        }
        .overlay(alignment: .bottom) { Rectangle().fill(DS.Palette.hairline).frame(height: DS.Stroke.hairline) }
        .overlay(alignment: .bottomLeading) { underline }
        .coordinateSpace(.named(Self.tabSpace))
        .onPreferenceChange(TabFramesKey.self) { tabFrames = $0 }
        .animation(DS.Motion.standard, value: page)
    }

    private static let tabSpace = "conversation.tabs"

    /// The underline slides with the pages: between the two labels in step with the swipe.
    @ViewBuilder
    private var underline: some View {
        if let summary = tabFrames[.summary], let transcript = tabFrames[.transcript] {
            let progress = pageProgress
            Rectangle()
                .fill(DS.Palette.ink)
                .frame(width: summary.width + (transcript.width - summary.width) * progress, height: 2)
                .offset(x: summary.minX + (transcript.minX - summary.minX) * progress)
                .allowsHitTesting(false)
        }
    }

    private func tab(_ title: String, _ value: Page) -> some View {
        // How selected this label is right now (follows the swipe).
        let weight = value == .summary ? 1 - pageProgress : pageProgress
        return Button {
            DSHaptics.selection()
            withAnimation(DS.Motion.standard) { page = value }
        } label: {
            Text(title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.Palette.inkTertiary)
                .overlay { Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(DS.Palette.ink).opacity(weight) }
                .padding(.bottom, DS.Spacing.sm)
                .background {
                    GeometryReader { proxy in
                        Color.clear.preference(key: TabFramesKey.self, value: [value: proxy.frame(in: .named(Self.tabSpace))])
                    }
                }
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(page == value ? .isSelected : [])
        .accessibilityIdentifier(value == .summary ? "conversation.tab.summary" : "conversation.tab.transcript")
    }

    /// The page the paging scroll view shows; a tap on a label scrolls there.
    private var pagePosition: Binding<Page?> {
        Binding(get: { page }, set: { if let value = $0 { page = value } })
    }

    /// `-omiSwipeDemo YES` pages to the transcript and back once the page has settled (a
    /// scripted check that the pager moves smoothly; Debug builds only).
    private func swipeForDebugging() async {
        #if DEBUG
            guard DebugLaunch.flag("omiSwipeDemo") else { return }
            for _ in 0 ..< 6 {
                try? await Task.sleep(for: .seconds(2.5))
                withAnimation(DS.Motion.standard) { page = page == .summary ? .transcript : .summary }
            }
        #endif
    }

    /// The action items as plain rows under the summary: check them off, or hand one to Omi.
    @ViewBuilder
    private var actionItems: some View {
        let canonical = tasks.tasks(forConversation: conversation.id)
        let fallback = store.detail?.summaryActionItems ?? []
        if !canonical.isEmpty || !fallback.isEmpty {
            VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                Text(L("nativeActionItems"))
                    .font(DS.Typography.sectionLabel)
                    .foregroundStyle(DS.Palette.inkSecondary)
                    .accessibilityAddTraits(.isHeader)
                if canonical.isEmpty {
                    ForEach(fallback, id: \.self) { text in
                        HStack(alignment: .firstTextBaseline, spacing: DS.Spacing.md) {
                            Image(systemName: "circle").font(.title3).foregroundStyle(DS.Palette.inkTertiary).accessibilityHidden(true)
                            Text(text).font(DS.Typography.body).foregroundStyle(DS.Palette.ink)
                        }
                        .padding(.vertical, DS.Spacing.xs)
                    }
                } else {
                    ForEach(canonical) { task in
                        TaskRow(
                            task,
                            agentStatus: AgentTaskStatus(task: task, agent: agent),
                            onToggle: { Task { await tasks.setCompleted(task.id, !task.isCompleted) } },
                            onHandOver: AgentTaskStatus(task: task, agent: agent) != nil || agent.canTakeOver(task)
                                ? { onHandOver(task) } : nil
                        )
                    }
                }
            }
        }
    }
}
