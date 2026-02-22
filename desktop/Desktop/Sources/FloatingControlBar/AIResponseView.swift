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

    var onClose: (() -> Void)?
    var onSendFollowUp: ((String) -> Void)?

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

                        // Current question
                        questionBar

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

            if !isLoading && !isVoiceFollowUp {
                followUpInputView
            }
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onExitCommand {
            onClose?()
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

            // modelPicker — moved to Settings > Ask Omi Floating Bar

            Button(action: { onClose?() }) {
                Image(systemName: "xmark")
                    .scaledFont(size: 8)
                    .foregroundColor(.secondary)
                    .frame(width: 16, height: 16)
                    .overlay(Circle().strokeBorder(Color.white.opacity(0.2), lineWidth: 0.5))
            }
            .buttonStyle(.plain)
        }
    }

    // MARK: - Content Blocks Rendering

    /// Renders a ChatMessage's content blocks using the shared components from ChatPage.
    @ViewBuilder
    private func contentBlocksView(for message: ChatMessage) -> some View {
        if !message.contentBlocks.isEmpty {
            let grouped = ContentBlockGroup.group(message.contentBlocks)
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
                }
            }
        } else if !message.text.isEmpty {
            SelectableMarkdown(text: message.text, sender: .ai)
                .textSelection(.enabled)
                .environment(\.colorScheme, .dark)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    // MARK: - Chat History

    private func chatExchangeView(_ exchange: FloatingChatExchange) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            // Question bubble
            HStack(alignment: .top, spacing: 8) {
                Text(exchange.question)
                    .scaledFont(size: 13)
                    .foregroundColor(.white)
                    .lineLimit(2)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color.white.opacity(0.1))
            .cornerRadius(8)

            // Response with content blocks
            contentBlocksView(for: exchange.aiMessage)
                .padding(.horizontal, 4)

            Divider()
                .background(Color.white.opacity(0.1))
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

    private var currentContentView: some View {
        Group {
            if let message = currentMessage {
                VStack(alignment: .leading, spacing: 4) {
                    contentBlocksView(for: message)

                    // Show typing indicator while streaming with no text yet
                    if message.isStreaming && message.text.isEmpty && message.contentBlocks.isEmpty {
                        TypingIndicator()
                    }
                }
                .padding(.horizontal, 4)
                .padding(.vertical, 8)
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

    private var followUpInputView: some View {
        HStack(spacing: 6) {
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

    private func sendFollowUp() {
        let trimmed = followUpText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        followUpText = ""
        onSendFollowUp?(trimmed)
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
