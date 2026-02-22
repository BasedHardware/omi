import SwiftUI
import MarkdownUI
import AppKit

// MARK: - Scroll Position Tracking

/// Detects scroll position changes by observing the underlying NSScrollView
struct ScrollPositionDetector: NSViewRepresentable {
    let onScrollPositionChange: (Bool) -> Void  // true if at bottom

    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        // Delay to ensure scroll view is in hierarchy
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            context.coordinator.setupScrollObserver(for: view)
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(onScrollPositionChange: onScrollPositionChange)
    }

    class Coordinator: NSObject {
        let onScrollPositionChange: (Bool) -> Void
        private var scrollView: NSScrollView?
        private var observation: NSObjectProtocol?
        /// Coalesces rapid bounds-change notifications so we update SwiftUI
        /// state at most once per ~60ms, preventing a feedback loop with
        /// programmatic scrolls during streaming.
        private var coalesceWorkItem: DispatchWorkItem?
        private var lastReportedValue: Bool?

        init(onScrollPositionChange: @escaping (Bool) -> Void) {
            self.onScrollPositionChange = onScrollPositionChange
        }

        func setupScrollObserver(for view: NSView) {
            // Find the enclosing NSScrollView
            var current: NSView? = view
            while let v = current {
                if let sv = v as? NSScrollView {
                    scrollView = sv
                    break
                }
                current = v.superview
            }

            guard let scrollView = scrollView else {
                return
            }
            let clipView = scrollView.contentView

            // Observe bounds changes (scroll events)
            clipView.postsBoundsChangedNotifications = true
            observation = NotificationCenter.default.addObserver(
                forName: NSView.boundsDidChangeNotification,
                object: clipView,
                queue: .main
            ) { [weak self] _ in
                self?.checkScrollPosition()
            }

            // Initial check
            checkScrollPosition()
        }

        func checkScrollPosition() {
            guard let scrollView = scrollView,
                  let documentView = scrollView.documentView else { return }

            let clipBounds = scrollView.contentView.bounds
            let documentHeight = documentView.frame.height
            let visibleMaxY = clipBounds.origin.y + clipBounds.height
            let threshold: CGFloat = 100

            // At bottom if we can see within threshold of the document bottom
            let isAtBottom = visibleMaxY >= documentHeight - threshold

            // Skip if the value hasn't changed — avoids redundant state updates
            guard isAtBottom != lastReportedValue else { return }

            // Coalesce rapid notifications into a single state update
            coalesceWorkItem?.cancel()
            let workItem = DispatchWorkItem { [weak self] in
                self?.lastReportedValue = isAtBottom
                self?.onScrollPositionChange(isAtBottom)
            }
            coalesceWorkItem = workItem
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.06, execute: workItem)
        }

        deinit {
            coalesceWorkItem?.cancel()
            if let observation = observation {
                NotificationCenter.default.removeObserver(observation)
            }
        }
    }
}

struct ChatPage: View {
    @ObservedObject var appProvider: AppProvider
    @ObservedObject var chatProvider: ChatProvider
    @State private var showAppPicker = false
    @State private var showHistoryPopover = false
    @State private var selectedCitation: Citation?
    @State private var citedConversation: ServerConversation?
    @State private var isLoadingCitation = false
    @State private var copied = false

    var selectedApp: OmiApp? {
        guard let appId = chatProvider.selectedAppId else { return nil }
        return appProvider.chatApps.first { $0.id == appId }
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header with app picker
            chatHeader
                .padding()

            Divider()
                .background(OmiColors.backgroundTertiary)

            // Messages area
            messagesView

            // Error banner
            if let error = chatProvider.errorMessage {
                HStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundColor(OmiColors.warning)
                        .scaledFont(size: 14)
                    Text(error)
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textSecondary)
                    Spacer()
                    Button {
                        chatProvider.errorMessage = nil
                    } label: {
                        Image(systemName: "xmark")
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                .background(OmiColors.backgroundSecondary)
            }

            // Input area
            inputArea
                .padding()
        }
        .background(OmiColors.backgroundPrimary)
        .sheet(item: $citedConversation) { conversation in
            ConversationDetailView(
                conversation: conversation,
                onBack: {
                    citedConversation = nil
                    selectedCitation = nil
                }
            )
            .frame(minWidth: 500, minHeight: 500)
        }
        .sheet(isPresented: $chatProvider.needsBrowserExtensionSetup) {
            BrowserExtensionSetup(
                onComplete: {
                    chatProvider.needsBrowserExtensionSetup = false
                },
                onDismiss: {
                    chatProvider.needsBrowserExtensionSetup = false
                },
                chatProvider: chatProvider
            )
            .fixedSize()
        }
        .sheet(isPresented: $chatProvider.isClaudeAuthRequired) {
            ClaudeAuthSheet(
                onConnect: {
                    chatProvider.startClaudeAuth()
                },
                onCancel: {
                    chatProvider.isClaudeAuthRequired = false
                    // Switch back to Mode A if auth cancelled
                    Task {
                        await chatProvider.switchBridgeMode(to: ChatProvider.BridgeMode.omiAI)
                    }
                }
            )
        }
        .overlay {
            // Loading overlay when fetching citation
            if isLoadingCitation {
                ZStack {
                    Color.black.opacity(0.3)
                    VStack(spacing: 12) {
                        ProgressView()
                        Text("Loading source...")
                            .scaledFont(size: 13)
                            .foregroundColor(.white)
                    }
                    .padding(20)
                    .background(OmiColors.backgroundSecondary)
                    .cornerRadius(12)
                }
            }
        }
    }

    // MARK: - Header

    private var chatHeader: some View {
        HStack {
            // Multi-chat mode controls
            if chatProvider.multiChatEnabled {
                // Default Chat indicator or button
                if chatProvider.isInDefaultChat {
                    // Show indicator that we're in default chat
                    HStack(spacing: 6) {
                        Image(systemName: "icloud")
                            .scaledFont(size: 11)
                        Text("Synced Chat")
                            .scaledFont(size: 11, weight: .medium)
                    }
                    .foregroundColor(OmiColors.success)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(OmiColors.success.opacity(0.15))
                    .cornerRadius(6)
                    .help("This chat syncs with your mobile app")
                } else {
                    // Show button to switch back to default chat
                    Button(action: {
                        Task {
                            await chatProvider.switchToDefaultChat()
                        }
                    }) {
                        HStack(spacing: 6) {
                            Image(systemName: "icloud")
                                .scaledFont(size: 11)
                            Text("Synced")
                                .scaledFont(size: 11, weight: .medium)
                        }
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(OmiColors.backgroundTertiary)
                        .cornerRadius(6)
                    }
                    .buttonStyle(.plain)
                    .help("Switch to synced chat (shares messages with mobile)")

                    // Current session indicator
                    if let session = chatProvider.currentSession {
                        Text(session.title)
                            .scaledFont(size: 12, weight: .medium)
                            .foregroundColor(OmiColors.textSecondary)
                            .lineLimit(1)
                    }
                }

                // New chat button
                Button(action: {
                    Task {
                        _ = await chatProvider.createNewSession()
                    }
                }) {
                    Image(systemName: "plus")
                        .scaledFont(size: 14, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
                .help("New chat session")
            }

            // App selector
            Button(action: { showAppPicker.toggle() }) {
                HStack(spacing: 10) {
                    if let app = selectedApp {
                        // Show selected app
                        AsyncImage(url: URL(string: app.image)) { phase in
                            switch phase {
                            case .success(let image):
                                image
                                    .resizable()
                                    .aspectRatio(contentMode: .fill)
                            default:
                                Circle()
                                    .fill(OmiColors.backgroundTertiary)
                            }
                        }
                        .frame(width: 32, height: 32)
                        .clipShape(Circle())

                        VStack(alignment: .leading, spacing: 2) {
                            Text(app.name)
                                .scaledFont(size: 14, weight: .medium)
                                .foregroundColor(OmiColors.textPrimary)

                            Text("Chat App")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                    } else {
                        // Default OMI assistant
                        Text("Omi")
                            .scaledFont(size: 14, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)
                    }

                    if !appProvider.chatApps.isEmpty {
                        Image(systemName: "chevron.down")
                            .scaledFont(size: 10)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(OmiColors.backgroundSecondary)
                .cornerRadius(20)
            }
            .buttonStyle(.plain)
            .disabled(appProvider.chatApps.isEmpty)
            .popover(isPresented: $showAppPicker, arrowEdge: .bottom) {
                AppPickerPopover(
                    apps: appProvider.chatApps,
                    selectedAppId: Binding(
                        get: { chatProvider.selectedAppId },
                        set: { newAppId in
                            Task {
                                await chatProvider.selectApp(newAppId)
                            }
                        }
                    ),
                    onSelect: { showAppPicker = false }
                )
            }

            Spacer()

            // Model indicator
            Text(chatProvider.currentModel)
                .scaledFont(size: 11)
                .foregroundColor(OmiColors.textTertiary)
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(OmiColors.backgroundSecondary)
                .cornerRadius(8)

            // Copy conversation button
            if !chatProvider.messages.isEmpty {
                Button(action: {
                    copyConversation()
                }) {
                    Image(systemName: copied ? "checkmark" : "doc.on.doc")
                        .scaledFont(size: 14)
                        .foregroundColor(copied ? OmiColors.success : OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
                .help("Copy conversation")
            }

            // Clear chat button
            if !chatProvider.messages.isEmpty || chatProvider.isClearing {
                Button(action: {
                    Task {
                        await chatProvider.clearChat()
                    }
                }) {
                    if chatProvider.isClearing {
                        ProgressView()
                            .scaleEffect(0.5)
                            .frame(width: 14, height: 14)
                    } else {
                        Image(systemName: "trash")
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                }
                .buttonStyle(.plain)
                .help("Clear chat history")
                .disabled(chatProvider.isLoading || chatProvider.isClearing)
            }

            // History button (only in multi-chat mode)
            if chatProvider.multiChatEnabled {
                Button(action: { showHistoryPopover.toggle() }) {
                    Image(systemName: "clock.arrow.circlepath")
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
                .help("Chat history")
                .popover(isPresented: $showHistoryPopover, arrowEdge: .bottom) {
                    ChatHistoryPopover(
                        chatProvider: chatProvider,
                        onSelect: { showHistoryPopover = false }
                    )
                }
            }

            // AI Chat settings button
            Button(action: {
                NotificationCenter.default.post(name: .navigateToAIChatSettings, object: nil)
            }) {
                Image(systemName: "gear")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textTertiary)
            }
            .buttonStyle(.plain)
            .help("AI Chat settings")
        }
    }

    // MARK: - Messages

    private var messagesView: some View {
        ChatMessagesView(
            messages: chatProvider.messages,
            isSending: chatProvider.isSending,
            hasMoreMessages: chatProvider.hasMoreMessages,
            isLoadingMoreMessages: chatProvider.isLoadingMoreMessages,
            isLoadingInitial: (chatProvider.isLoading || chatProvider.isLoadingSessions) && !chatProvider.isClearing,
            app: selectedApp,
            onLoadMore: { await chatProvider.loadMoreMessages() },
            onRate: { messageId, rating in
                Task { await chatProvider.rateMessage(messageId, rating: rating) }
            },
            onCitationTap: { citation in
                handleCitationTap(citation)
            },
            sessionsLoadError: chatProvider.sessionsLoadError,
            onRetry: { Task { await chatProvider.retryLoad() } },
            welcomeContent: { welcomeMessage }
        )
    }

    private var welcomeMessage: some View {
        VStack(spacing: 16) {
            if let app = selectedApp {
                AsyncImage(url: URL(string: app.image)) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                    default:
                        Circle()
                            .fill(OmiColors.backgroundTertiary)
                    }
                }
                .frame(width: 64, height: 64)
                .clipShape(Circle())

                Text("Chat with \(app.name)")
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Text(app.description)
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
                    .multilineTextAlignment(.center)
                    .lineLimit(3)
                    .padding(.horizontal, 40)
            } else {
                // Default OMI assistant
                if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
                   let logoImage = NSImage(contentsOf: logoURL) {
                    Image(nsImage: logoImage)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 48, height: 48)
                }

                Text("Chat with Omi")
                    .scaledFont(size: 18, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Text("Your personal AI assistant that knows you through your memories and conversations")
                    .scaledFont(size: 13)
                    .foregroundColor(OmiColors.textSecondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: - Input Area

    private var inputArea: some View {
        ChatInputView(
            onSend: { text in
                AnalyticsManager.shared.chatMessageSent(messageLength: text.count, hasContext: selectedApp != nil, source: "main_chat")
                Task { await chatProvider.sendMessage(text) }
            },
            onFollowUp: { text in
                Task { await chatProvider.sendFollowUp(text) }
            },
            onStop: {
                chatProvider.stopAgent()
            },
            isSending: chatProvider.isSending,
            isStopping: chatProvider.isStopping,
            mode: $chatProvider.chatMode,
            inputText: $chatProvider.draftText
        )
    }

    /// Copy the entire conversation to clipboard
    private func copyConversation() {
        let text: String = chatProvider.messages.map { message in
            let sender = message.sender == .user ? "You" : (selectedApp?.name ?? "Omi")
            return "\(sender): \(message.text)"
        }.joined(separator: "\n\n")

        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)

        copied = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            copied = false
        }
    }

    /// Handle tapping on a citation card
    private func handleCitationTap(_ citation: Citation) {
        guard citation.sourceType == .conversation else {
            // Memories don't have a detail view yet
            log("Citation tapped: \(citation.title) (memory - no detail view)")
            return
        }

        selectedCitation = citation
        isLoadingCitation = true

        // Fetch the full conversation
        Task {
            do {
                let conversation = try await APIClient.shared.getConversation(id: citation.id)
                await MainActor.run {
                    citedConversation = conversation
                    isLoadingCitation = false
                }
            } catch {
                logError("Failed to fetch cited conversation", error: error)
                await MainActor.run {
                    isLoadingCitation = false
                    selectedCitation = nil
                }
            }
        }
    }
}

// MARK: - Chat Bubble

struct ChatBubble: View {
    let message: ChatMessage
    let app: OmiApp?
    let onRate: (Int?) -> Void
    var onCitationTap: ((Citation) -> Void)? = nil
    var isDuplicate: Bool = false

    @State private var isHovering = false
    @State private var isExpanded = false
    @State private var showCopied = false

    /// Messages longer than this are truncated with a "Show more" button
    private static let truncationThreshold = 500

    /// Whether this message should be truncated
    private var shouldTruncate: Bool {
        !message.isStreaming && message.text.count > Self.truncationThreshold && !isExpanded
    }

    /// The text to display (truncated or full) — shows the END of the message
    private var displayText: String {
        if shouldTruncate {
            return "…" + String(message.text.suffix(Self.truncationThreshold))
        }
        return message.text
    }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            if message.sender == .ai {
                // App avatar
                if let app = app {
                    AsyncImage(url: URL(string: app.image)) { phase in
                        switch phase {
                        case .success(let image):
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                        default:
                            Circle()
                                .fill(OmiColors.backgroundTertiary)
                        }
                    }
                    .frame(width: 32, height: 32)
                    .clipShape(Circle())
                } else {
                    if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
                       let logoImage = NSImage(contentsOf: logoURL) {
                        Image(nsImage: logoImage)
                            .resizable()
                            .scaledToFit()
                            .frame(width: 20, height: 20)
                            .frame(width: 32, height: 32)
                            .background(OmiColors.backgroundTertiary)
                            .clipShape(Circle())
                    }
                }
            }

            VStack(alignment: message.sender == .user ? .trailing : .leading, spacing: 4) {
                if message.isStreaming && message.text.isEmpty && message.contentBlocks.isEmpty {
                    // Show typing indicator for empty streaming message
                    TypingIndicator()
                } else if message.sender == .ai && !message.contentBlocks.isEmpty {
                    // Render structured content blocks, grouping consecutive tool calls
                    let groupedBlocks = ContentBlockGroup.group(message.contentBlocks)
                    ForEach(groupedBlocks) { group in
                        switch group {
                        case .text(_, let text):
                            if !text.isEmpty {
                                SelectableMarkdown(text: text, sender: .ai)
                                    .padding(.horizontal, 14)
                                    .padding(.vertical, 10)
                                    .background(OmiColors.backgroundSecondary)
                                    .cornerRadius(18)
                            }
                        case .toolCalls(_, let calls):
                            ToolCallsGroup(calls: calls)
                        case .thinking(_, let text):
                            ThinkingBlock(text: text)
                        }
                    }
                    // Show typing indicator at end if still streaming
                    // (skip only when last group is tool calls with a running tool — it already has a spinner)
                    if message.isStreaming {
                        if case .toolCalls(_, let calls) = groupedBlocks.last,
                           calls.contains(where: { block in
                               if case .toolCall(_, _, .running, _, _, _) = block { return true }
                               return false
                           }) {
                            // Tool group has a running tool — its card already shows a spinner
                        } else {
                            TypingIndicator()
                        }
                    }
                } else if isDuplicate && !isExpanded {
                    // Collapsed duplicate message
                    Button(action: { isExpanded = true }) {
                        HStack(spacing: 6) {
                            Image(systemName: "doc.on.doc")
                                .scaledFont(size: 11)
                            Text("Duplicate message")
                                .scaledFont(size: 12)
                            Image(systemName: "chevron.down")
                                .scaledFont(size: 9)
                        }
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 8)
                        .background(OmiColors.backgroundTertiary.opacity(0.5))
                        .cornerRadius(18)
                    }
                    .buttonStyle(.plain)
                } else {
                    // User messages or AI messages without content blocks (loaded from Firestore)
                    VStack(alignment: message.sender == .user ? .trailing : .leading, spacing: 4) {
                        SelectableMarkdown(text: displayText, sender: message.sender)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 10)
                            .background(message.sender == .user ? OmiColors.purplePrimary : OmiColors.backgroundSecondary)
                            .cornerRadius(18)

                        // Show more / Show less toggle for long messages
                        if message.text.count > Self.truncationThreshold {
                            Button(action: { isExpanded.toggle() }) {
                                Text(isExpanded ? "Show less" : "Show more")
                                    .scaledFont(size: 11)
                                    .foregroundColor(.white)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }

                // Citation cards for AI messages with citations
                if message.sender == .ai && !message.citations.isEmpty && !message.isStreaming {
                    CitationCardsView(citations: message.citations) { citation in
                        onCitationTap?(citation)
                    }
                    .frame(maxWidth: 280)
                }

                // Rating buttons, copy button, and timestamp row for AI messages
                if message.sender == .ai && !message.isStreaming && message.isSynced {
                    HStack(spacing: 8) {
                        ratingButtons
                        copyButton

                        Text(message.createdAt, style: .time)
                            .scaledFont(size: 10)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                } else if message.sender == .ai && !message.isStreaming && !message.text.isEmpty {
                    HStack(spacing: 8) {
                        copyButton

                        Text(message.createdAt, style: .time)
                            .scaledFont(size: 10)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                } else if !message.isStreaming || !message.text.isEmpty {
                    Text(message.createdAt, style: .time)
                        .scaledFont(size: 10)
                        .foregroundColor(OmiColors.textTertiary)
                }
            }

            if message.sender == .user {
                // User avatar
                Image(systemName: "person.fill")
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textSecondary)
                    .frame(width: 32, height: 32)
                    .background(OmiColors.backgroundTertiary)
                    .clipShape(Circle())
            }
        }
        .frame(maxWidth: .infinity, alignment: message.sender == .user ? .trailing : .leading)
        .onHover { isHovering = $0 }
    }

    @ViewBuilder
    private var ratingButtons: some View {
        HStack(spacing: 4) {
            // Thumbs up
            Button(action: {
                // Toggle: if already thumbs up, clear rating; otherwise set thumbs up
                let newRating = message.rating == 1 ? nil : 1
                onRate(newRating)
            }) {
                Image(systemName: message.rating == 1 ? "hand.thumbsup.fill" : "hand.thumbsup")
                    .scaledFont(size: 11)
                    .foregroundColor(message.rating == 1 ? OmiColors.purplePrimary : OmiColors.textTertiary)
            }
            .buttonStyle(.plain)
            .help("Helpful response")

            // Thumbs down
            Button(action: {
                // Toggle: if already thumbs down, clear rating; otherwise set thumbs down
                let newRating = message.rating == -1 ? nil : -1
                onRate(newRating)
            }) {
                Image(systemName: message.rating == -1 ? "hand.thumbsdown.fill" : "hand.thumbsdown")
                    .scaledFont(size: 11)
                    .foregroundColor(message.rating == -1 ? .red : OmiColors.textTertiary)
            }
            .buttonStyle(.plain)
            .help("Not helpful")
        }
    }

    @ViewBuilder
    private var copyButton: some View {
        Button(action: {
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(message.text, forType: .string)
            showCopied = true
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                showCopied = false
            }
        }) {
            Image(systemName: showCopied ? "checkmark" : "doc.on.doc")
                .scaledFont(size: 11)
                .foregroundColor(showCopied ? .green : OmiColors.textTertiary)
        }
        .buttonStyle(.plain)
        .help("Copy message")
    }
}

// MARK: - Content Block Grouping

/// Groups consecutive tool call blocks into a single collapsible group
enum ContentBlockGroup: Identifiable {
    case text(id: String, text: String)
    case toolCalls(id: String, calls: [ChatContentBlock])
    case thinking(id: String, text: String)

    var id: String {
        switch self {
        case .text(let id, _): return id
        case .toolCalls(let id, _): return id
        case .thinking(let id, _): return id
        }
    }

    /// Groups consecutive `.toolCall` blocks together; passes `.text` and `.thinking` through
    static func group(_ blocks: [ChatContentBlock]) -> [ContentBlockGroup] {
        var groups: [ContentBlockGroup] = []
        var pendingToolCalls: [ChatContentBlock] = []

        func flushToolCalls() {
            guard !pendingToolCalls.isEmpty else { return }
            let groupId = "toolgroup_\(pendingToolCalls.first!.id)"
            groups.append(.toolCalls(id: groupId, calls: pendingToolCalls))
            pendingToolCalls = []
        }

        for block in blocks {
            switch block {
            case .text(let id, let text):
                flushToolCalls()
                groups.append(.text(id: id, text: text))
            case .toolCall:
                pendingToolCalls.append(block)
            case .thinking(let id, let text):
                flushToolCalls()
                groups.append(.thinking(id: id, text: text))
            }
        }
        flushToolCalls()
        return groups
    }
}

// MARK: - Tool Calls Group

/// Renders a group of consecutive tool calls as a single collapsed summary line
struct ToolCallsGroup: View {
    let calls: [ChatContentBlock]

    @State private var isExpanded = false

    /// Whether any tool in the group is still running
    private var hasRunningTool: Bool {
        calls.contains { block in
            if case .toolCall(_, _, .running, _, _, _) = block { return true }
            return false
        }
    }

    /// Display name of the currently running tool (last running one), or last tool if all done
    private var currentToolName: String {
        // Find the last running tool
        if let lastRunning = calls.last(where: { block in
            if case .toolCall(_, _, .running, _, _, _) = block { return true }
            return false
        }) {
            if case .toolCall(_, let name, _, _, _, _) = lastRunning {
                return ChatContentBlock.displayName(for: name)
            }
        }
        // All done — show last tool name
        if case .toolCall(_, let name, _, _, _, _) = calls.last {
            return ChatContentBlock.displayName(for: name)
        }
        return "Working"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Summary header
            Button(action: {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            }) {
                HStack(spacing: 6) {
                    // Status indicator
                    if hasRunningTool {
                        ProgressView()
                            .controlSize(.mini)
                            .frame(width: 12, height: 12)
                    } else {
                        Image(systemName: "checkmark.circle.fill")
                            .scaledFont(size: 12)
                            .foregroundColor(.green)
                    }

                    // Current/last tool action
                    Text(currentToolName)
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textSecondary)

                    // Step count (only show when > 1)
                    if calls.count > 1 {
                        Text("·")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)
                        Text("\(calls.count) steps")
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.textTertiary)
                    }

                    Spacer(minLength: 4)

                    // Expand chevron
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .scaledFont(size: 9)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
            }
            .buttonStyle(.plain)

            // Expanded: show individual tool call cards
            if isExpanded {
                Divider()
                    .padding(.horizontal, 8)

                VStack(alignment: .leading, spacing: 4) {
                    ForEach(calls) { block in
                        if case .toolCall(_, let name, let status, _, let input, let output) = block {
                            ToolCallCard(name: name, status: status, input: input, output: output)
                        }
                    }
                }
                .padding(.horizontal, 6)
                .padding(.vertical, 6)
            }
        }
        .background(OmiColors.backgroundTertiary.opacity(0.5))
        .cornerRadius(8)
    }
}

// MARK: - Tool Call Card

struct ToolCallCard: View {
    let name: String
    let status: ToolCallStatus
    let input: ToolCallInput?
    let output: String?

    @State private var isExpanded = false

    private var hasExpandableContent: Bool {
        input?.details != nil || output != nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Compact header row
            Button(action: {
                if hasExpandableContent {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        isExpanded.toggle()
                    }
                }
            }) {
                HStack(spacing: 6) {
                    // Status indicator
                    if status == .running {
                        ProgressView()
                            .controlSize(.mini)
                            .frame(width: 12, height: 12)
                    } else {
                        Image(systemName: "checkmark.circle.fill")
                            .scaledFont(size: 12)
                            .foregroundColor(.green)
                    }

                    // Tool name
                    Text(ChatContentBlock.displayName(for: name))
                        .scaledFont(size: 12, design: .monospaced)
                        .foregroundColor(OmiColors.textSecondary)

                    // Inline argument summary
                    if let summary = input?.summary {
                        Text("·")
                            .scaledFont(size: 12)
                            .foregroundColor(OmiColors.textTertiary)

                        Text(summary)
                            .scaledFont(size: 11, design: .monospaced)
                            .foregroundColor(OmiColors.textTertiary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }

                    Spacer(minLength: 4)

                    // Expand chevron
                    if hasExpandableContent {
                        Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                            .scaledFont(size: 9)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
            }
            .buttonStyle(.plain)

            // Expanded content
            if isExpanded {
                Divider()
                    .padding(.horizontal, 8)

                VStack(alignment: .leading, spacing: 8) {
                    // Input details
                    if let details = input?.details {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Input")
                                .scaledFont(size: 10, weight: .semibold)
                                .foregroundColor(OmiColors.textTertiary)

                            Text(details)
                                .scaledFont(size: 11, design: .monospaced)
                                .foregroundColor(OmiColors.textSecondary)
                                .lineLimit(10)
                        }
                    }

                    // Output
                    if let output = output, !output.isEmpty {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Output")
                                .scaledFont(size: 10, weight: .semibold)
                                .foregroundColor(OmiColors.textTertiary)

                            Text(output)
                                .scaledFont(size: 11, design: .monospaced)
                                .foregroundColor(OmiColors.textSecondary)
                                .lineLimit(15)
                        }
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
            }
        }
        .background(OmiColors.backgroundTertiary.opacity(0.5))
        .cornerRadius(8)
    }
}

// MARK: - Thinking Block

struct ThinkingBlock: View {
    let text: String

    @State private var isExpanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            Button(action: {
                withAnimation(.easeInOut(duration: 0.2)) {
                    isExpanded.toggle()
                }
            }) {
                HStack(spacing: 6) {
                    Image(systemName: "brain")
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textTertiary)

                    Text("Thinking")
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(OmiColors.textTertiary)
                        .italic()

                    Spacer(minLength: 4)

                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .scaledFont(size: 9)
                        .foregroundColor(OmiColors.textTertiary)
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
            }
            .buttonStyle(.plain)

            // Expanded thinking content
            if isExpanded {
                Divider()
                    .padding(.horizontal, 8)

                Text(text)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textTertiary)
                    .italic()
                    .padding(.horizontal, 10)
                    .padding(.vertical, 8)
                    .lineLimit(30)
            }
        }
        .background(OmiColors.backgroundTertiary.opacity(0.3))
        .cornerRadius(8)
    }
}

// MARK: - Typing Indicator

struct TypingIndicator: View {
    @State private var animationPhase = 0

    var body: some View {
        HStack(spacing: 4) {
            ForEach(0..<3, id: \.self) { index in
                Circle()
                    .fill(OmiColors.textTertiary)
                    .frame(width: 8, height: 8)
                    .scaleEffect(animationPhase == index ? 1.2 : 0.8)
                    .animation(.easeInOut(duration: 0.4).repeatForever().delay(Double(index) * 0.15), value: animationPhase)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(OmiColors.backgroundSecondary)
        .cornerRadius(18)
        .onAppear {
            animationPhase = 1
        }
    }
}

// MARK: - App Picker Popover

struct AppPickerPopover: View {
    let apps: [OmiApp]
    @Binding var selectedAppId: String?
    let onSelect: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Select Assistant")
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(OmiColors.textTertiary)
                .padding(.horizontal, 12)
                .padding(.top, 12)
                .padding(.bottom, 8)

            ScrollView {
                VStack(spacing: 2) {
                    // Default OMI option
                    DefaultOmiRow(isSelected: selectedAppId == nil) {
                        selectedAppId = nil
                        AnalyticsManager.shared.chatAppSelected(appId: nil, appName: "OMI")
                        onSelect()
                    }

                    if !apps.isEmpty {
                        Divider()
                            .padding(.vertical, 4)
                            .padding(.horizontal, 12)

                        ForEach(apps) { app in
                            AppPickerRow(
                                app: app,
                                isSelected: selectedAppId == app.id
                            ) {
                                selectedAppId = app.id
                                AnalyticsManager.shared.chatAppSelected(appId: app.id, appName: app.name)
                                onSelect()
                            }
                        }
                    }
                }
            }
            .frame(maxHeight: 300)
        }
        .frame(width: 250)
        .background(OmiColors.backgroundPrimary)
    }
}

struct DefaultOmiRow: View {
    let isSelected: Bool
    let onSelect: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: onSelect) {
            HStack(spacing: 10) {
                if let logoURL = Bundle.resourceBundle.url(forResource: "herologo", withExtension: "png"),
                   let logoImage = NSImage(contentsOf: logoURL) {
                    Image(nsImage: logoImage)
                        .resizable()
                        .scaledToFit()
                        .frame(width: 22, height: 22)
                        .frame(width: 36, height: 36)
                        .background(OmiColors.backgroundTertiary)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                }

                Text("Omi")
                    .scaledFont(size: 13, weight: .medium)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                if isSelected {
                    Image(systemName: "checkmark")
                        .scaledFont(size: 12, weight: .semibold)
                        .foregroundColor(OmiColors.purplePrimary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(isSelected || isHovering ? OmiColors.backgroundSecondary : Color.clear)
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
    }
}

struct AppPickerRow: View {
    let app: OmiApp
    let isSelected: Bool
    let onSelect: () -> Void

    @State private var isHovering = false

    var body: some View {
        Button(action: onSelect) {
            HStack(spacing: 10) {
                AsyncImage(url: URL(string: app.image)) { phase in
                    switch phase {
                    case .success(let image):
                        image
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                    default:
                        Circle()
                            .fill(OmiColors.backgroundTertiary)
                    }
                }
                .frame(width: 36, height: 36)
                .clipShape(RoundedRectangle(cornerRadius: 8))

                VStack(alignment: .leading, spacing: 2) {
                    Text(app.name)
                        .scaledFont(size: 13, weight: .medium)
                        .foregroundColor(OmiColors.textPrimary)

                    Text(app.author)
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textTertiary)
                }

                Spacer()

                if isSelected {
                    Image(systemName: "checkmark")
                        .scaledFont(size: 12, weight: .semibold)
                        .foregroundColor(OmiColors.purplePrimary)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(isSelected || isHovering ? OmiColors.backgroundSecondary : Color.clear)
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
    }
}

// MARK: - Chat History Popover

struct ChatHistoryPopover: View {
    @ObservedObject var chatProvider: ChatProvider
    let onSelect: () -> Void

    @State private var isTogglingStarred = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack {
                Text("Chat History")
                    .scaledFont(size: 14, weight: .semibold)
                    .foregroundColor(OmiColors.textPrimary)

                Spacer()

                // Starred filter button
                Button(action: {
                    Task {
                        isTogglingStarred = true
                        await chatProvider.toggleStarredFilter()
                        isTogglingStarred = false
                    }
                }) {
                    if isTogglingStarred {
                        ProgressView()
                            .scaleEffect(0.5)
                            .frame(width: 14, height: 14)
                    } else {
                        Image(systemName: chatProvider.showStarredOnly ? "star.fill" : "star")
                            .scaledFont(size: 12)
                            .foregroundColor(chatProvider.showStarredOnly ? OmiColors.amber : OmiColors.textTertiary)
                    }
                }
                .buttonStyle(.plain)
                .help(chatProvider.showStarredOnly ? "Show all chats" : "Show starred only")

                // New chat button in header
                Button(action: {
                    Task {
                        _ = await chatProvider.createNewSession()
                        onSelect()
                    }
                }) {
                    Image(systemName: "plus")
                        .scaledFont(size: 12, weight: .medium)
                        .foregroundColor(OmiColors.purplePrimary)
                }
                .buttonStyle(.plain)
                .help("New chat")
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)

            // Search field
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .scaledFont(size: 11)
                    .foregroundColor(OmiColors.textTertiary)

                TextField("Search chats...", text: $chatProvider.searchQuery)
                    .textFieldStyle(.plain)
                    .scaledFont(size: 12)
                    .foregroundColor(OmiColors.textPrimary)

                if !chatProvider.searchQuery.isEmpty {
                    Button(action: { chatProvider.searchQuery = "" }) {
                        Image(systemName: "xmark.circle.fill")
                            .scaledFont(size: 11)
                            .foregroundColor(OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(OmiColors.backgroundSecondary)
            .cornerRadius(6)
            .padding(.horizontal, 16)
            .padding(.bottom, 12)

            Divider()

            // Sessions list
            if chatProvider.isLoadingSessions {
                VStack {
                    Spacer()
                    ProgressView()
                        .scaleEffect(0.8)
                    Text("Loading...")
                        .scaledFont(size: 12)
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.top, 8)
                    Spacer()
                }
                .frame(height: 200)
            } else if chatProvider.filteredSessions.isEmpty {
                VStack(spacing: 8) {
                    Spacer()
                    Image(systemName: emptyStateIcon)
                        .scaledFont(size: 24)
                        .foregroundColor(OmiColors.textTertiary)
                    Text(emptyStateTitle)
                        .scaledFont(size: 13)
                        .foregroundColor(OmiColors.textSecondary)
                    Text(emptyStateSubtitle)
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textTertiary)
                    Spacer()
                }
                .frame(height: 200)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        ForEach(chatProvider.groupedSessions, id: \.0) { group, sessions in
                            // Group header
                            Text(group)
                                .scaledFont(size: 11, weight: .semibold)
                                .foregroundColor(OmiColors.textTertiary)
                                .padding(.horizontal, 16)
                                .padding(.top, 12)
                                .padding(.bottom, 6)

                            // Sessions in group
                            ForEach(sessions) { session in
                                HistorySessionRow(
                                    session: session,
                                    isSelected: chatProvider.currentSession?.id == session.id,
                                    isDeleting: chatProvider.deletingSessionIds.contains(session.id),
                                    onSelect: {
                                        Task {
                                            await chatProvider.selectSession(session)
                                            onSelect()
                                        }
                                    },
                                    onDelete: {
                                        Task {
                                            await chatProvider.deleteSession(session)
                                        }
                                    },
                                    onToggleStar: {
                                        Task {
                                            await chatProvider.toggleStarred(session)
                                        }
                                    },
                                    onRename: { newTitle in
                                        Task {
                                            await chatProvider.updateSessionTitle(session, title: newTitle)
                                        }
                                    }
                                )
                            }
                        }
                    }
                    .padding(.bottom, 12)
                }
                .frame(maxHeight: 400)
            }
        }
        .frame(width: 320)
        .background(OmiColors.backgroundPrimary)
    }

    private var emptyStateIcon: String {
        if !chatProvider.searchQuery.isEmpty {
            return "magnifyingglass"
        } else if chatProvider.showStarredOnly {
            return "star"
        } else {
            return "bubble.left.and.bubble.right"
        }
    }

    private var emptyStateTitle: String {
        if !chatProvider.searchQuery.isEmpty {
            return "No results"
        } else if chatProvider.showStarredOnly {
            return "No starred chats"
        } else {
            return "No chats yet"
        }
    }

    private var emptyStateSubtitle: String {
        if !chatProvider.searchQuery.isEmpty {
            return "Try a different search"
        } else if chatProvider.showStarredOnly {
            return "Star a chat to see it here"
        } else {
            return "Start a conversation"
        }
    }
}

// MARK: - History Session Row

struct HistorySessionRow: View {
    let session: ChatSession
    let isSelected: Bool
    var isDeleting: Bool = false
    let onSelect: () -> Void
    let onDelete: () -> Void
    let onToggleStar: () -> Void
    let onRename: (String) -> Void

    @State private var isHovering = false
    @State private var showDeleteConfirm = false
    @State private var isEditing = false
    @State private var editedTitle = ""
    @FocusState private var isTitleFocused: Bool

    var body: some View {
        Button(action: {
            if !isEditing {
                onSelect()
            }
        }) {
            HStack(spacing: 8) {
                // Star indicator
                if session.starred {
                    Image(systemName: "star.fill")
                        .scaledFont(size: 10)
                        .foregroundColor(.yellow)
                }

                VStack(alignment: .leading, spacing: 2) {
                    if isEditing {
                        TextField("Chat title", text: $editedTitle)
                            .textFieldStyle(.plain)
                            .scaledFont(size: 13, weight: isSelected ? .semibold : .regular)
                            .foregroundColor(isSelected ? OmiColors.purplePrimary : OmiColors.textPrimary)
                            .focused($isTitleFocused)
                            .onSubmit { saveTitle() }
                            .onExitCommand { cancelEditing() }
                    } else {
                        Text(session.title)
                            .scaledFont(size: 13, weight: isSelected ? .semibold : .regular)
                            .foregroundColor(isSelected ? OmiColors.purplePrimary : OmiColors.textPrimary)
                            .lineLimit(1)
                    }

                    if !isEditing {
                        HStack(spacing: 4) {
                            if let preview = session.preview, !preview.isEmpty {
                                Text(preview)
                                    .lineLimit(1)
                            }
                            Text("·")
                            Text(session.createdAt, style: .relative)
                        }
                        .scaledFont(size: 11)
                        .foregroundColor(OmiColors.textTertiary)
                        .lineLimit(1)
                    }
                }

                Spacer()

                if isDeleting {
                    ProgressView()
                        .scaleEffect(0.5)
                        .frame(width: 14, height: 14)
                }

                // Action buttons on hover
                if isHovering && !isEditing && !isDeleting {
                    HStack(spacing: 6) {
                        // Rename button
                        Button(action: startEditing) {
                            Image(systemName: "pencil")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)

                        // Star button
                        Button(action: onToggleStar) {
                            Image(systemName: session.starred ? "star.fill" : "star")
                                .scaledFont(size: 11)
                                .foregroundColor(session.starred ? .yellow : OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)

                        // Delete button
                        Button(action: { showDeleteConfirm = true }) {
                            Image(systemName: "trash")
                                .scaledFont(size: 11)
                                .foregroundColor(OmiColors.textTertiary)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(isSelected ? OmiColors.backgroundSecondary : (isHovering ? OmiColors.backgroundSecondary.opacity(0.5) : Color.clear))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { isHovering = $0 }
        .onTapGesture(count: 2) { startEditing() }
        .alert("Delete Chat?", isPresented: $showDeleteConfirm) {
            Button("Cancel", role: .cancel) {}
            Button("Delete", role: .destructive) {
                onDelete()
            }
        } message: {
            Text("This will permanently delete this chat and all its messages.")
        }
    }

    private func startEditing() {
        editedTitle = session.title
        isEditing = true
        isTitleFocused = true
    }

    private func saveTitle() {
        let trimmed = editedTitle.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty && trimmed != session.title {
            onRename(trimmed)
        }
        isEditing = false
    }

    private func cancelEditing() {
        isEditing = false
        editedTitle = session.title
    }
}

#Preview {
    ChatPage(appProvider: AppProvider(), chatProvider: ChatProvider())
        .frame(width: 600, height: 700)
}

// MARK: - Markdown Themes

extension Theme {
    static func userMessage(scale: CGFloat = 1.0) -> Theme {
        Theme()
            .text {
                ForegroundColor(.white)
                FontSize(round(14 * scale))
            }
            .code {
                FontFamilyVariant(.monospaced)
                FontSize(round(13 * scale))
                ForegroundColor(.white.opacity(0.9))
                BackgroundColor(.white.opacity(0.15))
            }
            .strong {
                FontWeight(.semibold)
            }
            .link {
                ForegroundColor(.white.opacity(0.9))
                UnderlineStyle(.single)
            }
    }

    static func aiMessage(scale: CGFloat = 1.0) -> Theme {
        Theme()
            .text {
                ForegroundColor(OmiColors.textPrimary)
                FontSize(round(14 * scale))
            }
            .code {
                FontFamilyVariant(.monospaced)
                FontSize(round(13 * scale))
                ForegroundColor(OmiColors.textPrimary)
                BackgroundColor(OmiColors.backgroundTertiary)
            }
            .codeBlock { configuration in
                ScrollView(.horizontal, showsIndicators: false) {
                    configuration.label
                        .markdownTextStyle {
                            FontFamilyVariant(.monospaced)
                            FontSize(round(13 * scale))
                            ForegroundColor(OmiColors.textPrimary)
                        }
                }
                .padding(12)
                .background(OmiColors.backgroundTertiary)
                .cornerRadius(8)
            }
            .strong {
                FontWeight(.semibold)
            }
            .link {
                ForegroundColor(OmiColors.purplePrimary)
            }
    }
}

struct ScaledMarkdownTheme: ViewModifier {
    @Environment(\.fontScale) private var fontScale
    let sender: ChatSender

    func body(content: Content) -> some View {
        content.markdownTheme(sender == .user ? .userMessage(scale: fontScale) : .aiMessage(scale: fontScale))
    }
}

extension View {
    func scaledMarkdownTheme(_ sender: ChatSender) -> some View {
        modifier(ScaledMarkdownTheme(sender: sender))
    }
}
