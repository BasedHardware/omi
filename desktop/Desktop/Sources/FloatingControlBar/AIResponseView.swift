import SwiftUI

/// Streaming markdown response view for the floating control bar.
struct AIResponseView: View {
    @EnvironmentObject var state: FloatingControlBarState
    @Binding var isLoading: Bool
    let currentMessage: ChatMessage?
    @State private var isQuestionExpanded = false
    @State private var followUpText: String = ""
    @FocusState private var isFollowUpFocused: Bool

    let userInput: String
    let chatHistory: [FloatingChatExchange]
    @Binding var isVoiceFollowUp: Bool
    @Binding var voiceFollowUpTranscript: String
    var canClearVisibleConversation: Bool = false

    var onClearVisibleConversation: (() -> Void)?
    var onEscape: (() -> Void)?
    var onSendFollowUp: ((String) -> Void)?
    var onRate: ((String, Int?) -> Void)?
    var onShareLink: (() async -> String?)?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            headerView
                .fixedSize(horizontal: false, vertical: true)

            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 16) {
                        // Previous chat exchanges
                        ForEach(chatHistory) { exchange in
                            chatExchangeView(exchange)
                        }

                        if hasUserInput(userInput) {
                            questionBar
                        }

                        // Current response
                        currentContentView

                        // Voice follow-up indicator (shown inline when PTT is active during conversation)
                        if isVoiceFollowUp {
                            voiceFollowUpView
                                .id("voiceFollowUp")
                        }

                        // Anchor for auto-scroll
                        Color.clear.frame(height: 1).id("bottom")
                    }
                    .background(
                        GeometryReader { geo -> Color in
                            let h = geo.size.height
                            DispatchQueue.main.async {
                                state.responseContentHeight = h
                            }
                            return Color.clear
                        }
                    )
                }
                .onChange(of: currentMessage?.text) {
                    withAnimation(.easeOut(duration: 0.15)) {
                        proxy.scrollTo("bottom", anchor: .bottom)
                    }
                }
                .onChange(of: currentMessage?.contentBlocks.count) {
                    withAnimation(.easeOut(duration: 0.15)) {
                        proxy.scrollTo("bottom", anchor: .bottom)
                    }
                }
                .onChange(of: chatHistory.count) {
                    withAnimation(.easeOut(duration: 0.15)) {
                        proxy.scrollTo("bottom", anchor: .bottom)
                    }
                }
                .onChange(of: isVoiceFollowUp) {
                    if isVoiceFollowUp {
                        withAnimation(.easeOut(duration: 0.15)) {
                            proxy.scrollTo("voiceFollowUp", anchor: .bottom)
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            if let shareFeedbackMessage, showShareFeedback {
                shareFeedbackBanner
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .accessibilityLabel(shareFeedbackMessage)
            }

            if !isLoading && !isVoiceFollowUp {
                followUpInputView
            }
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .animation(.spring(response: 0.28, dampingFraction: 0.85), value: showShareFeedback)
        .onExitCommand {
            onEscape?()
        }
        .onAppear {
            if !isLoading {
                // Restored conversation: focus follow-up field immediately
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                    isFollowUpFocused = true
                }
            }
        }
        .onChange(of: isLoading) {
            if !isLoading {
                // Auto-focus follow-up field when loading finishes
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                    isFollowUpFocused = true
                }
            }
        }
    }

    private var headerView: some View {
        HStack(spacing: 12) {
            if isLoading {
                ProgressView()
                    .scaleEffect(0.6)
                    .frame(width: 16, height: 16)
                Text("thinking")
                    .scaledFont(size: 14)
                    .foregroundColor(.secondary)
            } else {
                Text("omi says")
                    .scaledFont(size: 14)
                    .foregroundColor(.secondary)
            }

            Spacer()

            if canClearVisibleConversation {
                HStack(spacing: 4) {
                    Text("esc")
                        .scaledFont(size: 11)
                        .foregroundColor(.secondary)
                        .frame(width: 30, height: 16)
                        .background(Color.white.opacity(0.1))
                        .cornerRadius(4)
                    Text("to clear")
                        .scaledFont(size: 11)
                        .foregroundColor(.secondary)
                }
            }
        }
    }

    // MARK: - Content Blocks Rendering

    /// Renders a ChatMessage's content blocks using the shared components from ChatPage.
    @ViewBuilder
    private func contentBlocksView(for message: ChatMessage) -> some View {
        if !message.contentBlocks.isEmpty {
            let grouped = groupedContentBlocks(for: message)
            ForEach(grouped) { group in
                switch group {
                case .text(_, let text):
                    SelectableMarkdown(text: text, sender: .ai)
                        .textSelection(.enabled)
                        .environment(\.colorScheme, .dark)
                        .frame(maxWidth: .infinity, alignment: .leading)
                case .toolCalls(_, let calls):
                    ToolCallsGroup(calls: calls)
                        .frame(maxWidth: .infinity, alignment: .leading)
                case .thinking(_, let text):
                    ThinkingBlock(text: text)
                        .frame(maxWidth: .infinity, alignment: .leading)
                case .discoveryCard(_, let title, let summary, let fullText):
                    DiscoveryCard(title: title, summary: summary, fullText: fullText)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        } else if !message.text.isEmpty {
            SelectableMarkdown(text: message.text, sender: .ai)
                .textSelection(.enabled)
                .environment(\.colorScheme, .dark)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func groupedContentBlocks(for message: ChatMessage) -> [ContentBlockGroup] {
        let grouped = ContentBlockGroup.group(message.contentBlocks)
        guard !message.isStreaming else { return grouped }

        return grouped.filter { group in
            switch group {
            case .text, .discoveryCard:
                return true
            case .toolCalls, .thinking:
                return false
            }
        }
    }

    // MARK: - Per-Message Hover Action Overlay

    /// Wraps an AI message's content with a hover-triggered action bar.
    /// The `.id(message.id)` is load-bearing: without it SwiftUI can reuse an
    /// overlay view instance (and its Button action closures) across different
    /// messages in the same structural slot, which caused clicking Copy on an
    /// older message to read the current message's text.
    private func messageWithHoverActions(message: ChatMessage) -> some View {
        MessageHoverOverlay(
            message: message,
            onRate: { [id = message.id] rating in
                onRate?(id, rating)
            }
        )
        {
            contentBlocksView(for: message)
        }
        .id(message.id)
    }

    // MARK: - Chat History

    private func chatExchangeView(_ exchange: FloatingChatExchange) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if hasUserInput(exchange.question) {
                HStack(alignment: .top, spacing: 8) {
                    Text(exchange.question ?? "")
                        .scaledFont(size: 13)
                        .foregroundColor(.white)
                        .lineLimit(2)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color.white.opacity(0.1))
                .cornerRadius(8)
            }

            // Response with hover actions
            messageWithHoverActions(message: exchange.aiMessage)
                .padding(.horizontal, 4)
        }
    }

    // MARK: - Current Question & Response

    private var questionBar: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 8) {
                Group {
                    if isQuestionExpanded {
                        ScrollView {
                            Text(userInput)
                                .scaledFont(size: 13)
                                .foregroundColor(.white)
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .frame(maxHeight: 120)
                    } else {
                        Text(userInput)
                            .scaledFont(size: 13)
                            .foregroundColor(.white)
                            .lineLimit(1)
                            .truncationMode(.head)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }

                if needsExpansion {
                    Button(action: { isQuestionExpanded.toggle() }) {
                        Image(systemName: isQuestionExpanded ? "chevron.up" : "chevron.down")
                            .scaledFont(size: 10)
                            .foregroundColor(.secondary)
                            .frame(width: 20, height: 20)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color.white.opacity(0.1))
            .cornerRadius(8)
            .contextMenu {
                Button("Copy") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(userInput, forType: .string)
                }
            }
        }
    }

    private var needsExpansion: Bool {
        let font = NSFont.systemFont(ofSize: 13)
        let attributes = [NSAttributedString.Key.font: font]
        let size = (userInput as NSString).boundingRect(
            with: NSSize(width: 350, height: CGFloat.greatestFiniteMagnitude),
            options: .usesLineFragmentOrigin,
            attributes: attributes
        ).size
        return size.height > font.pointSize * 1.5
    }

    private func hasUserInput(_ text: String?) -> Bool {
        guard let text else { return false }
        return !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var currentContentView: some View {
        Group {
            if let message = currentMessage {
                VStack(alignment: .leading, spacing: 4) {
                    if message.isStreaming {
                        // While streaming, show content without hover actions
                        contentBlocksView(for: message)

                        if message.text.isEmpty && message.contentBlocks.isEmpty {
                            TypingIndicator()
                        }
                    } else {
                        // After streaming completes, show with hover actions
                        messageWithHoverActions(message: message)
                    }
                }
                .padding(.horizontal, 4)
                .padding(.bottom, 6)
                .contextMenu {
                    Button("Copy") {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(message.text, forType: .string)
                    }
                    Button("Copy Question & Answer") {
                        let combined = "Q: \(userInput)\n\nA: \(message.text)"
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(combined, forType: .string)
                    }
                }
            } else {
                TypingIndicator()
                    .frame(maxWidth: .infinity, minHeight: 40, alignment: .leading)
                    .padding(.horizontal, 4)
            }
        }
    }

    // MARK: - Voice Follow-Up

    private var voiceFollowUpView: some View {
        HStack(spacing: 8) {
            Circle()
                .fill(Color.red)
                .frame(width: 10, height: 10)
                .scaleEffect(1.2)
                .animation(.easeInOut(duration: 0.6).repeatForever(autoreverses: true), value: isVoiceFollowUp)

            Image(systemName: "mic.fill")
                .scaledFont(size: 14, weight: .semibold)
                .foregroundColor(.white)

            if !voiceFollowUpTranscript.isEmpty {
                Text(voiceFollowUpTranscript)
                    .scaledFont(size: 13)
                    .foregroundColor(.white.opacity(0.8))
                    .lineLimit(2)
                    .truncationMode(.head)
            } else {
                Text("Listening...")
                    .scaledFont(size: 13)
                    .foregroundColor(.white.opacity(0.5))
            }

            Spacer()
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(Color.red.opacity(0.15))
        .cornerRadius(8)
    }

    // MARK: - Follow-Up Input

    @State private var showShareFeedback = false
    @State private var shareFeedbackMessage: String?
    @State private var shareFeedbackHideWorkItem: DispatchWorkItem?
    @State private var isSharingLink = false

    private var followUpInputView: some View {
        HStack(spacing: 6) {
            Button(action: { shareLink() }) {
                Image(systemName: showShareFeedback ? "checkmark" : "arrowshape.turn.up.right")
                    .scaledFont(size: 13)
                    .foregroundColor(showShareFeedback ? .green : .secondary)
            }
            .buttonStyle(.plain)
            .help("Copy share link")
            .disabled(isSharingLink)

            TextField("Ask follow up...", text: $followUpText)
                .textFieldStyle(.plain)
                .scaledFont(size: 13)
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(Color.white.opacity(0.1))
                .cornerRadius(8)
                .focused($isFollowUpFocused)
                .onSubmit {
                    sendFollowUp()
                }

            Button(action: { sendFollowUp() }) {
                Image(systemName: "arrow.up.circle.fill")
                    .scaledFont(size: 20)
                    .foregroundColor(
                        followUpText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                            ? .secondary : .white
                    )
            }
            .disabled(followUpText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            .buttonStyle(.plain)
        }
    }

    private var shareFeedbackBanner: some View {
        HStack(spacing: 8) {
            Image(systemName: "checkmark.circle.fill")
                .scaledFont(size: 12, weight: .semibold)
                .foregroundColor(.green)

            Text("Share link copied to your clipboard")
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(.white)

            Spacer(minLength: 0)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
        .background(Color.green.opacity(0.18))
        .overlay(
            RoundedRectangle(cornerRadius: 8)
                .strokeBorder(Color.green.opacity(0.35), lineWidth: 1)
        )
        .cornerRadius(8)
    }

    private func shareLink() {
        guard !isSharingLink else { return }
        isSharingLink = true
        Task {
            if let url = await onShareLink?() {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.setString(url, forType: .string)
                AnalyticsManager.shared.shareAction(category: "floating_bar_share_link")
                showShareSuccessFeedback()
            }
            isSharingLink = false
        }
    }

    private func showShareSuccessFeedback() {
        shareFeedbackHideWorkItem?.cancel()
        shareFeedbackMessage = "Share link copied to your clipboard"
        withAnimation {
            showShareFeedback = true
        }

        let workItem = DispatchWorkItem {
            withAnimation {
                showShareFeedback = false
                shareFeedbackMessage = nil
            }
        }
        shareFeedbackHideWorkItem = workItem
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.8, execute: workItem)
    }

    private func sendFollowUp() {
        let trimmed = followUpText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        followUpText = ""
        onSendFollowUp?(trimmed)
    }
}

// MARK: - Message Hover Overlay

/// Overlay that shows action buttons (thumbs up/down, copy, info) on hover over an AI message
struct MessageHoverOverlay<Content: View>: View {
    let message: ChatMessage
    let onRate: (Int?) -> Void
    @ViewBuilder let content: () -> Content

    @State private var isHovered = false
    @State private var isBarHovered = false
    @State private var showCopied = false
    @State private var showInfoPopover = false
    @State private var hideWorkItem: DispatchWorkItem?
    @State private var showRatingFeedback = false
    @State private var lastSubmittedRating: Int?

    private var shouldShowBar: Bool {
        (isHovered || isBarHovered || showInfoPopover) && !message.isStreaming
    }

    private var actionBarWidth: CGFloat {
        message.metadata == nil ? 56 : 76
    }

    var body: some View {
        ZStack(alignment: .topTrailing) {
            VStack(alignment: .leading, spacing: 8) {
                content()
            }
            .padding(.trailing, actionBarWidth)

            actionBar
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .onHover { hovering in
            if hovering {
                // Show immediately
                hideWorkItem?.cancel()
                hideWorkItem = nil
                withAnimation(.easeInOut(duration: 0.15)) {
                    isHovered = true
                }
            } else {
                // Delay hide by 1.5s so user can move cursor to the buttons
                let work = DispatchWorkItem {
                    withAnimation(.easeInOut(duration: 0.15)) {
                        isHovered = false
                    }
                }
                hideWorkItem = work
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.5, execute: work)
            }
        }
    }

    private var actionBar: some View {
        // Capture the message's value-type fields once per body evaluation so every
        // button action operates on the exact message the user sees — not whatever
        // `self.message` happens to point to when the click is dispatched.
        let messageText = message.text
        let currentRating = message.rating
        return VStack(alignment: .trailing, spacing: 2) {
            HStack(spacing: 6) {
                // Thumbs up
                Button(action: { [currentRating] in
                    let newRating = currentRating == 1 ? nil : 1
                    guard newRating != lastSubmittedRating else { return }
                    lastSubmittedRating = newRating
                    onRate(newRating)
                    if newRating != nil { showRatingFeedbackBriefly() }
                }) {
                    Image(systemName: currentRating == 1 ? "hand.thumbsup.fill" : "hand.thumbsup")
                        .scaledFont(size: 11)
                        .foregroundColor(currentRating == 1 ? .green : .secondary)
                }
                .buttonStyle(.plain)
                .help("Helpful response")

                // Thumbs down
                Button(action: { [currentRating] in
                    let newRating = currentRating == -1 ? nil : -1
                    guard newRating != lastSubmittedRating else { return }
                    lastSubmittedRating = newRating
                    onRate(newRating)
                    if newRating != nil { showRatingFeedbackBriefly() }
                }) {
                    Image(systemName: currentRating == -1 ? "hand.thumbsdown.fill" : "hand.thumbsdown")
                        .scaledFont(size: 11)
                        .foregroundColor(currentRating == -1 ? .red : .secondary)
                }
                .buttonStyle(.plain)
                .help("Not helpful")

                // Copy — captures `messageText` explicitly so we always copy the
                // message this button was drawn for, even if SwiftUI reuses the
                // overlay view across re-renders.
                Button(action: { [messageText] in copyText(messageText) }) {
                    Image(systemName: showCopied ? "checkmark" : "doc.on.doc")
                        .scaledFont(size: 11)
                        .foregroundColor(showCopied ? .green : .secondary)
                }
                .buttonStyle(.plain)
                .help("Copy response")

                // Info (developer context)
                if message.metadata != nil {
                    Button(action: { showInfoPopover.toggle() }) {
                        Image(systemName: "info.circle")
                            .scaledFont(size: 11)
                            .foregroundColor(showInfoPopover ? .white : .secondary)
                    }
                    .buttonStyle(.plain)
                    .help("View response context")
                    .popover(isPresented: $showInfoPopover, arrowEdge: .bottom) {
                        MessageMetadataPopover(metadata: message.metadata!)
                    }
                }
            }

            if showRatingFeedback {
                Text("Thank you!")
                    .scaledFont(size: 9)
                    .foregroundColor(.secondary)
                    .transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: showRatingFeedback)
        .frame(width: actionBarWidth, alignment: .trailing)
        .padding(.top, 1)
        .opacity(shouldShowBar ? 1 : 0)
        .allowsHitTesting(shouldShowBar)
        .animation(.easeInOut(duration: 0.15), value: shouldShowBar)
        .onHover { hovering in
            isBarHovered = hovering
            if hovering {
                // Cancel any pending hide
                hideWorkItem?.cancel()
                hideWorkItem = nil
            }
        }
    }

    private func showRatingFeedbackBriefly() {
        showRatingFeedback = true
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            showRatingFeedback = false
        }
    }

    /// Copy the exact text passed in — *not* `self.message.text`.
    /// Callers must pass the captured text from the closure's capture list so
    /// clicking Copy on a historical message writes the correct content to the
    /// pasteboard even when SwiftUI has reused the overlay view across renders.
    private func copyText(_ text: String) {
        guard !text.isEmpty else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        AnalyticsManager.shared.shareAction(category: "floating_bar_response_copy")
        withAnimation { showCopied = true }
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            withAnimation { showCopied = false }
        }
    }
}

// MARK: - Metadata Popover

/// Developer popover showing full context used to generate an AI response
struct MessageMetadataPopover: View {
    let metadata: MessageMetadata

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                // Header
                Text("Response Context")
                    .font(.headline)
                    .foregroundColor(.primary)

                // Key info
                if let model = metadata.model {
                    metadataRow(label: "Model", value: model)
                }
                if metadata.hasScreenshot, let size = metadata.screenshotSizeBytes {
                    let kb = size / 1024
                    let base64Chars = (size * 4 + 2) / 3  // base64 expansion
                    metadataRow(label: "Screenshot", value: "1 image (\(kb) KB, ~\(base64Chars / 1024) KB base64)")
                } else {
                    metadataRow(label: "Screenshot", value: "None")
                }

                Divider()

                // Context fed into the prompt
                Text("Context in Prompt")
                    .scaledFont(size: 11, weight: .semibold)
                    .foregroundColor(.primary)
                metadataRow(label: "User memories/facts", value: "\(metadata.memoriesCount)")
                metadataRow(label: "Conversation history turns", value: "\(metadata.conversationTurns)")
                metadataRow(label: "Tasks", value: "\(metadata.tasksCount)")
                metadataRow(label: "Goals", value: "\(metadata.goalsCount)")
                metadataRow(label: "Available tools", value: "\(metadata.availableToolsCount)")

                // Tool calls
                if !metadata.toolNames.isEmpty {
                    Divider()
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Tools used (\(metadata.toolNames.count))")
                            .scaledFont(size: 11, weight: .semibold)
                            .foregroundColor(.primary)
                        ForEach(metadata.toolNames, id: \.self) { tool in
                            Text("  \(tool)")
                                .scaledFont(size: 11)
                                .foregroundColor(.secondary)
                                .textSelection(.enabled)
                        }
                        if metadata.sqlQueryCount > 0 {
                            metadataRow(
                                label: "SQL queries",
                                value: "\(metadata.sqlQueryCount) queries, \(metadata.sqlRowsReturned) rows returned"
                            )
                        }
                    }
                }

                // Full system prompt — always expanded, scrollable
                if let prompt = metadata.systemPrompt, !prompt.isEmpty {
                    Divider()
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("Full System Prompt")
                                .scaledFont(size: 11, weight: .semibold)
                                .foregroundColor(.primary)
                            Spacer()
                            Text("\(prompt.count) chars")
                                .scaledFont(size: 10)
                                .foregroundColor(.secondary)
                            Button(action: {
                                NSPasteboard.general.clearContents()
                                NSPasteboard.general.setString(prompt, forType: .string)
                            }) {
                                Image(systemName: "doc.on.doc")
                                    .scaledFont(size: 10)
                                    .foregroundColor(.secondary)
                            }
                            .buttonStyle(.plain)
                            .help("Copy prompt")
                        }
                        Text(prompt)
                            .scaledFont(size: 10)
                            .foregroundColor(.primary)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            .padding()
            .frame(width: 450)
        }
        .frame(width: 450, height: 500)
    }

    private func metadataRow(label: String, value: String) -> some View {
        HStack {
            Text(label)
                .scaledFont(size: 11)
                .foregroundColor(.secondary)
            Spacer()
            Text(value)
                .scaledFont(size: 11, weight: .medium)
                .foregroundColor(.primary)
                .textSelection(.enabled)
        }
    }
}

// MARK: - Model Menu Helper

class ModelMenuTarget: NSObject {
    static let shared = ModelMenuTarget()
    var onSelect: ((String) -> Void)?

    @objc func selectModel(_ sender: NSMenuItem) {
        if let modelId = sender.representedObject as? String {
            onSelect?(modelId)
        }
    }
}
