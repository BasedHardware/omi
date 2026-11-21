import OmiComponents
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// One row of the thread: a message, hand-overs that finished while the app was open (a run of
/// them in a row is one stack), or the line where a new day starts.
enum ChatRow: Identifiable {
    case message(ChatMessage)
    case run(AgentStore.Run)
    case runs([AgentStore.Run])
    case day(Date)

    var id: String {
        switch self {
        case let .message(message): message.id
        case let .run(run): "run-\(run.id)"
        case let .runs(runs): "runs-\(runs.first?.id ?? "")"
        case let .day(date): "day-\(Int(date.timeIntervalSince1970))"
        }
    }

    private var date: Date? {
        switch self {
        case let .message(message): message.createdAt
        case let .run(run): run.finishedAt ?? run.startedAt
        case let .runs(runs): runs.first.flatMap { $0.finishedAt ?? $0.startedAt }
        case .day: nil
        }
    }

    /// Finished runs in a row become one stack (the first and "2 more"): never two such cards in a row.
    static func stacked(_ rows: [ChatRow]) -> [ChatRow] {
        ChatStacking.stacks(rows) { row in
            if case .run = row { "run" } else { row.id }
        }
        .map { stack in
            guard stack.count > 1 else { return stack[0] }
            return .runs(stack.compactMap { if case let .run(run) = $0 { run } else { nil } })
        }
    }

    /// Messages in their order, each finished run (oldest first) before the first message that
    /// came after it ended, and a day line before the first row of every day.
    static func merge(_ messages: [ChatMessage], _ runs: [AgentStore.Run], calendar: Calendar = .current) -> [ChatRow] {
        var rows: [ChatRow] = []
        var pending = runs[...]
        for message in messages {
            while let run = pending.first, (run.finishedAt ?? run.startedAt) < message.createdAt {
                rows.append(.run(run))
                pending.removeFirst()
            }
            rows.append(.message(message))
        }
        rows += pending.map(ChatRow.run)
        var dated: [ChatRow] = []
        var lastDay: Date?
        for row in rows {
            if let date = row.date {
                let day = calendar.startOfDay(for: date)
                if day != lastDay { dated.append(.day(day)) }
                lastDay = day
            }
            dated.append(row)
        }
        return dated
    }
}

/// The top bar (sheet or tab), Running now, searching the thread, and what the shell asks for.
extension ChatScreen {
    /// The full-screen chat: close, who you talk to, "…". The tab has no bar of its own (the app
    /// header above holds search and "…"): only the search field while searching, the offline
    /// line and Running now, each only while it applies.
    var header: some View {
        VStack(spacing: DS.Spacing.sm) {
            if mode == .sheet { titleRow }
            if isSearching { searchBar }
            if network.isOffline { OfflineHint() }
            if mode == .tab, !isSearching { RunningStrip { open($0) } }
        }
        // Full width even when empty: its fade spans the page.
        .frame(maxWidth: .infinity)
        .padding(.horizontal, DS.Spacing.lg)
        .padding(.top, mode == .sheet ? DS.Spacing.sm : 0)
        .padding(.bottom, hasTopBar ? DS.Spacing.sm : 0)
        .animation(DS.Motion.gentle, value: network.isOffline)
        .animation(DS.Motion.snappy, value: agent.activeRuns.map(\.id))
        .animation(DS.Motion.snappy, value: isSearching)
    }

    private var hasTopBar: Bool {
        mode == .sheet || isSearching || network.isOffline || !agent.activeRuns.isEmpty
    }

    private var titleRow: some View {
        HStack {
            CircleIconButton("xmark") { dismiss() }.accessibilityLabel(L("close"))
            Spacer()
            ChatAppPicker()
            Spacer()
            if chat.hasLoaded, !chat.messages.isEmpty {
                ChatMenu(showsTalkTo: false)
            } else {
                Color.clear.frame(width: DS.Size.headerButton, height: DS.Size.headerButton)
            }
        }
    }

    /// One message with what its long-press menu and swipe do.
    func bubble(_ message: ChatMessage, position: ChatGrouping.Position) -> some View {
        let isLast = message.id == chat.messages.last?.id
        let failed = message.sender == .user ? chat.failedAnswer(after: message.id) : nil
        return MessageBubble(
            message: message,
            isStreaming: chat.isStreaming && isLast,
            isLatest: isLast,
            position: position,
            // Only the newest answer offers a follow-up; the others need not redraw while typing.
            draftIsEmpty: !isLast || draft.isEmpty,
            onRetry: { chat.retry(message.id) },
            onTryAgain: failed.map { answer in { chat.retry(answer.id) } },
            onReply: { reply(to: message) },
            onDelete: {
                withAnimation(DS.Motion.snappy) { chat.hide(message.id) }
            },
            onOpenConversation: openConversation,
            onUpgrade: onUpgrade,
            onFollowUp: { send($0) },
            onSend: { send($0) },
            onAskAboutFile: { file in
                draft = L("nativeChatAboutFileDraft", file.name)
                composerFocused = true
            }
        )
    }

    /// "Reply" from a bubble: the composer shows what it answers and the keyboard comes up.
    func reply(to message: ChatMessage) {
        DSHaptics.selection()
        withAnimation(DS.Motion.snappy) { chat.replyingTo = message }
        composerFocused = true
    }

    private var searchBar: some View {
        VStack(alignment: .leading, spacing: DS.Spacing.sm) {
            HStack(spacing: DS.Spacing.md) {
                OmiSearchField(L("nativeChatSearchPrompt"), text: $query, clearLabel: L("nativeChatSearchClear"))
                    .focused($searchFocused)
                    .accessibilityIdentifier("chat.searchField")
                Button(L("cancel")) { stopSearching() }
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.ink)
                    .buttonStyle(.plain)
            }
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: DS.Spacing.sm) {
                    ForEach(ChatThreadFilter.allCases, id: \.self) { item in
                        Button {
                            DSHaptics.selection()
                            filter = filter == item ? nil : item
                        } label: {
                            OmiChip(
                                ChatThreadFilter.title(item), systemImage: ChatThreadFilter.symbol(item),
                                tint: filter == item ? DS.Palette.agent : nil
                            )
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(filter == item ? .isSelected : [])
                        .accessibilityIdentifier("chat.filter.\(item.rawValue)")
                    }
                }
            }
        }
        .transition(.opacity)
    }

    var isFiltering: Bool {
        isSearching && (!query.trimmingCharacters(in: .whitespaces).isEmpty || filter != nil)
    }

    func startSearching() {
        DSHaptics.selection()
        composerFocused = false
        isSearching = true
        searchFocused = true
    }

    func stopSearching() {
        isSearching = false
        query = ""
        filter = nil
        searchFocused = false
    }

    /// Hand-overs that ended while the app was open, oldest first.
    var finishedRuns: [AgentStore.Run] {
        agent.runs.values
            .filter { !$0.isActive && $0.finishedAt != nil }
            .sorted { ($0.finishedAt ?? .distantPast) < ($1.finishedAt ?? .distantPast) }
    }

    var rows: [ChatRow] {
        ChatRow.stacked(ChatRow.merge(chat.messages, chat.chatApp == nil ? finishedRuns : []))
    }

    /// Where each message sits in its group: steps or cards above an answer start a new group,
    /// anything below one (sources, a chart, a failure) ends it.
    func groupPositions(_ rows: [ChatRow]) -> [String: ChatGrouping.Position] {
        let latest = chat.messages.last?.id
        return ChatGrouping.positions(rows.map { row in
            guard case let .message(message) = row else { return ChatGrouping.Item(id: row.id, sender: nil) }
            guard message.sender == .omi else {
                return ChatGrouping.Item(id: message.id, sender: .user, date: message.createdAt, leadsWithExtras: !message.files.isEmpty)
            }
            let leads = message.steps.contains { !AgentStore.isHeartbeat($0) } || !chat.cards(for: message.id).isEmpty
                || chat.pendingDeviceToolMessageID == message.id
            let ends = !message.citations().isEmpty || message.chart != nil || message.failure != nil || message.isServiceFailure
                || (message.id == latest && message.followUp != nil) || voice.playingID == message.id
            return ChatGrouping.Item(id: message.id, sender: .omi, date: message.createdAt, leadsWithExtras: leads, endsWithExtras: ends)
        })
    }

    /// Room above a row: a few points inside a group, more between groups.
    static func gap(before row: ChatRow, at index: Int, positions: [String: ChatGrouping.Position]) -> CGFloat {
        guard index > 0 else { return 0 }
        if case .message = row, positions[row.id]?.isFirst == false { return MessageBubble.groupSpacing }
        return DS.Spacing.md
    }

    /// The matches while searching, in thread order (the newest by the composer): a tap goes back
    /// to the full thread at that one.
    @ViewBuilder
    func matches(_ proxy: ScrollViewProxy) -> some View {
        let found = chat.visibleMessages(query: query, filter: filter)
        let runs = filter == .jobs && query.isEmpty ? finishedRuns : []
        if found.isEmpty, runs.isEmpty {
            Text(L("nativeChatSearchNothing"))
                .font(DS.Typography.callout)
                .foregroundStyle(DS.Palette.inkSecondary)
                .frame(maxWidth: .infinity)
                .padding(.top, DS.Spacing.xl * 2)
        }
        ForEach(runs) { run in
            RunOutcomeRow(run: run) { open(run) }
        }
        ForEach(found) { message in
            SearchMatchRow(message: message) {
                stopSearching()
                jumpTarget = message.id
            }
        }
    }

    func open(_ run: AgentStore.Run) {
        DSHaptics.selection()
        composerFocused = false
        openRun = tasks.tasks.first { $0.id == run.id } ?? ActionItem(
            id: run.id, description: run.taskTitle, isCompleted: false, dueAt: nil, conversationID: nil,
            owner: .user, workstreamID: run.workstreamID, createdAt: nil
        )
    }

    /// A source chip or reference: the shell opens the conversation (closing the chat page); the
    /// tab without a handler goes through the app's link (`omi://conversation/<id>`).
    var openConversation: (String) -> Void {
        if let onOpenConversation { return onOpenConversation }
        let openURL = openURL
        return { openURL(DeepLink.conversation(id: $0).url) }
    }

    func conversationTitle(for task: ActionItem) -> String? {
        task.conversationID.flatMap { id in conversations.conversations.first { $0.id == id }?.title }
    }

    /// The shell switched to the tab with something to do: a draft in the composer, or listening.
    func handle(_ request: Request?) async {
        guard let request, handledRequest != request.id else { return }
        handledRequest = request.id
        if request.search {
            if let wanted = request.filter {
                // A filter from the header's "…": the matches, without the keyboard in the way.
                composerFocused = false
                isSearching = true
                filter = wanted
            } else if isSearching {
                searchFocused = true
            } else {
                startSearching()
            }
            return
        }
        stopSearching()
        if !request.draft.isEmpty { draft = request.draft }
        if request.dictate { await startDictation() }
    }
}

/// A message found by search or a filter: who, when, a few lines.
private struct SearchMatchRow: View {
    let message: ChatMessage
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: DS.Spacing.xs) {
                HStack(spacing: DS.Spacing.xs) {
                    Text(message.sender == .user ? L("nativeChatYou") : "Omi").font(DS.Typography.caption.weight(.semibold))
                    Text(message.createdAt.formatted(.dateTime.day().month(.abbreviated).hour().minute()))
                        .font(DS.Typography.caption)
                        .foregroundStyle(DS.Palette.inkTertiary)
                    if !message.files.isEmpty {
                        Image(systemName: "paperclip").imageScale(.small).foregroundStyle(DS.Palette.inkTertiary)
                    }
                }
                Text(message.text.isEmpty ? message.files.map(\.name).joined(separator: ", ") : ChatQuote.split(message.text).body)
                    .font(DS.Typography.callout)
                    .foregroundStyle(DS.Palette.ink)
                    .lineLimit(3)
                    .multilineTextAlignment(.leading)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(DS.Spacing.md)
            .background(DS.Palette.card, in: RoundedRectangle(cornerRadius: DS.Radius.card, style: .continuous))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("chat.match")
    }
}
