import MarkdownUI
import SwiftUI

/// Streaming markdown response view for the floating control bar.
struct AIResponseView: View {
    @EnvironmentObject var state: FloatingControlBarState
    @Binding var isLoading: Bool
    @Binding var responseText: String
    @State private var isQuestionExpanded = false
    @State private var followUpText: String = ""
    @FocusState private var isFollowUpFocused: Bool

    let userInput: String
    let chatHistory: [ChatExchange]
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
                .onChange(of: responseText) {
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

            modelPicker

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

    private var modelPicker: some View {
        HStack(spacing: 2) {
            Text(currentModelLabel)
            Image(systemName: "chevron.down")
                .imageScale(.small)
        }
        .scaledFont(size: 14)
        .foregroundColor(.secondary)
        .fixedSize()
        .contentShape(Rectangle())
        .onTapGesture {
            showModelMenu()
        }
    }

    private func showModelMenu() {
        let menu = NSMenu()
        for model in FloatingControlBarState.availableModels {
            let item = NSMenuItem(title: model.label, action: #selector(ModelMenuTarget.selectModel(_:)), keyEquivalent: "")
            item.state = state.selectedModel == model.id ? .on : .off
            item.representedObject = model.id
            item.target = ModelMenuTarget.shared
            menu.addItem(item)
        }
        ModelMenuTarget.shared.onSelect = { [state] modelId in
            state.selectedModel = modelId
        }
        if let event = NSApp.currentEvent, let contentView = event.window?.contentView {
            menu.popUp(positioning: nil, at: event.locationInWindow, in: contentView)
        }
    }

    private var currentModelLabel: String {
        FloatingControlBarState.availableModels.first { $0.id == state.selectedModel }?.label ?? "Sonnet"
    }

    // MARK: - Chat History

    private func chatExchangeView(_ exchange: ChatExchange) -> some View {
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

            // Response
            Markdown(exchange.response)
                .scaledMarkdownTheme(.ai)
                .textSelection(.enabled)
                .environment(\.colorScheme, .dark)
                .frame(maxWidth: .infinity, alignment: .leading)
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
            if responseText.isEmpty {
                ThinkingDotsView()
                    .frame(maxWidth: .infinity, minHeight: 40, alignment: .leading)
                    .padding(.horizontal, 4)
            } else if !responseText.isEmpty {
                Markdown(responseText)
                    .scaledMarkdownTheme(.ai)
                    .textSelection(.enabled)
                    .environment(\.colorScheme, .dark)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 4)
                    .padding(.vertical, 8)
                    .contextMenu {
                        Button("Copy") {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(responseText, forType: .string)
                        }
                        Button("Copy Question & Answer") {
                            let combined = "Q: \(userInput)\n\nA: \(responseText)"
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(combined, forType: .string)
                        }
                    }
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

// MARK: - Thinking Animation

/// Animated dots that pulse sequentially to indicate AI is processing.
struct ThinkingDotsView: View {
    @State private var activeDot = 0

    private let dotCount = 3
    private let dotSize: CGFloat = 6
    private let timer = Timer.publish(every: 0.4, on: .main, in: .common).autoconnect()

    var body: some View {
        HStack(spacing: 5) {
            ForEach(0..<dotCount, id: \.self) { index in
                Circle()
                    .fill(Color.white.opacity(index == activeDot ? 0.9 : 0.25))
                    .frame(width: dotSize, height: dotSize)
                    .scaleEffect(index == activeDot ? 1.3 : 1.0)
                    .animation(.easeInOut(duration: 0.3), value: activeDot)
            }
        }
        .onReceive(timer) { _ in
            activeDot = (activeDot + 1) % dotCount
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
