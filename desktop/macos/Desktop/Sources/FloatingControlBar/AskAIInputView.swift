import AppKit
import SwiftUI
import UniformTypeIdentifiers
import OmiTheme

/// "Ask a question..." input panel for the floating control bar.
struct AskAIInputView: View {
    @EnvironmentObject var state: FloatingControlBarState
    @Binding var userInput: String
    @State private var textHeight: CGFloat = 40
    @State private var hasMarkedText = false
    @State private var attachments: [ChatAttachment] = []
    @State private var isDropTargeted = false

    var canClearVisibleConversation: Bool = false
    var onSend: ((String) -> Void)?
    var onClearVisibleConversation: (() -> Void)?
    var onEscape: (() -> Void)?
    var onHeightChange: ((CGFloat) -> Void)?

    private let minHeight: CGFloat = 40
    private let maxHeight: CGFloat = 200
    private var trimmedInput: String { userInput.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var canSend: Bool {
        !hasMarkedText && (!trimmedInput.isEmpty || !attachments.isEmpty)
    }

    var body: some View {
        VStack(spacing: 0) {
            if canClearVisibleConversation {
                HStack {
                    Spacer()

                    HStack(spacing: OmiSpacing.xxs) {
                        Text("esc")
                            .scaledFont(size: OmiType.caption)
                            .foregroundColor(.secondary)
                            .frame(width: 30, height: 16)
                            .background(Color.white.opacity(0.1))
                            .cornerRadius(OmiChrome.stripRadius)
                        Text("to clear")
                            .scaledFont(size: OmiType.caption)
                            .foregroundColor(.secondary)
                    }
                }
                .padding(.top, OmiSpacing.sm)
                .padding(.trailing, OmiSpacing.lg)
            }

            if !attachments.isEmpty {
                AttachmentPreviewRow(
                    attachments: attachments,
                    onRemove: removeAttachment
                )
                .environment(\.colorScheme, .dark)
                .padding(.horizontal, OmiSpacing.lg)
                .padding(.top, OmiSpacing.sm)
            }

            HStack(spacing: OmiSpacing.xs) {
                ZStack(alignment: .topLeading) {
                    if userInput.isEmpty && !hasMarkedText {
                        Text("Ask a question...")
                            .scaledFont(size: OmiType.body)
                            .foregroundColor(.secondary)
                            .padding(.horizontal, OmiSpacing.sm)
                            .padding(.vertical, OmiSpacing.sm)
                    }

                    OmiTextEditor(
                        text: $userInput,
                        lineFragmentPadding: 8,
                        onSubmit: {
                            guard canSend else { return }
                            sendMessage()
                        },
                        focusOnAppear: true,
                        onMarkedTextChange: { hasMarkedText = $0 },
                        minHeight: minHeight,
                        maxHeight: maxHeight,
                        onHeightChange: { newHeight in
                            if abs(textHeight - newHeight) > 1 {
                                textHeight = newHeight
                                onHeightChange?(newHeight)
                            }
                        }
                    )
                }
                .padding(.horizontal, OmiSpacing.xxs)
                .frame(height: textHeight)

                Button(action: {
                    guard canSend else { return }
                    sendMessage()
                }) {
                    Image(systemName: "arrow.up.circle.fill")
                        .scaledFont(size: 24)
                        .foregroundColor(
                            canSend ? .white : .secondary
                        )
                }
                .disabled(!canSend)
                .buttonStyle(.plain)
            }
            .padding(.horizontal, OmiSpacing.lg)
            .padding(.vertical, OmiSpacing.md)
            .frame(maxWidth: .infinity)
        }
        .onDrop(of: [UTType.fileURL], isTargeted: $isDropTargeted, perform: handleAttachmentDrop)
        .onExitCommand {
            onEscape?()
        }
    }

    private func sendMessage() {
        let text = trimmedInput
        let staged = attachments
        guard !text.isEmpty || !staged.isEmpty else { return }
        userInput = text
        attachments = []
        if !staged.isEmpty {
            FloatingControlBarManager.shared.sharedFloatingProvider?.addAttachments(staged)
        }
        onSend?(text)
    }

    private func handleAttachmentDrop(providers: [NSItemProvider]) -> Bool {
        ChatAttachmentDropHandler.collectURLs(from: providers) { urls in
            addAttachmentURLs(urls)
        }
    }

    private func addAttachmentURLs(_ urls: [URL]) {
        let remaining = max(0, kMaxChatAttachments - attachments.count)
        guard remaining > 0 else { return }
        let staged = urls.prefix(remaining).compactMap(ChatAttachment.from(url:))
        guard !staged.isEmpty else { return }
        attachments.append(contentsOf: staged)
    }

    private func removeAttachment(_ id: String) {
        attachments.removeAll { $0.id == id }
    }
}
