import SwiftUI

/// Reusable chat input field with send button, extracted from ChatPage.
/// Used by both ChatPage (main chat) and TaskChatPanel (task sidebar chat).
///
/// When `isSending` is true:
///   - Input stays enabled so the user can type a follow-up
///   - If input is empty, the button becomes a stop button
///   - If input has text, pressing send calls `onFollowUp` (redirects the agent)
struct ChatInputView: View {
    let onSend: (String) -> Void
    var onFollowUp: ((String) -> Void)? = nil
    var onStop: (() -> Void)? = nil
    let isSending: Bool
    var placeholder: String = "Type a message..."
    @Binding var mode: ChatMode

    @State private var inputText = ""
    @FocusState private var isInputFocused: Bool

    private var hasText: Bool {
        !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        HStack(spacing: 12) {
            TextField(placeholder, text: $inputText, axis: .vertical)
                .textFieldStyle(.plain)
                .scaledFont(size: 14)
                .foregroundColor(OmiColors.textPrimary)
                .focused($isInputFocused)
                .padding(12)
                .lineLimit(1...5)
                .onSubmit {
                    handleSubmit()
                }
                .frame(maxWidth: .infinity)
                .background(OmiColors.backgroundSecondary)
                .cornerRadius(20)
                .contentShape(Rectangle())
                .onTapGesture {
                    isInputFocused = true
                }
                .onAppear {
                    isInputFocused = true
                }

            // Ask/Act mode toggle
            ChatModeToggle(mode: $mode)

            if isSending && !hasText {
                // Stop button — visible when agent is running and input is empty
                Button(action: { onStop?() }) {
                    Image(systemName: "stop.circle.fill")
                        .scaledFont(size: 32)
                        .foregroundColor(.red.opacity(0.8))
                }
                .buttonStyle(.plain)
            } else {
                // Send / follow-up button
                Button(action: handleSubmit) {
                    Image(systemName: "arrow.up.circle.fill")
                        .scaledFont(size: 32)
                        .foregroundColor(hasText ? OmiColors.purplePrimary : OmiColors.textTertiary)
                }
                .buttonStyle(.plain)
                .disabled(!hasText)
            }
        }
    }

    private func handleSubmit() {
        guard hasText else { return }
        let text = inputText
        inputText = ""
        if isSending {
            onFollowUp?(text)
        } else {
            onSend(text)
        }
    }
}

// MARK: - Ask/Act Mode Toggle

struct ChatModeToggle: View {
    @Binding var mode: ChatMode

    var body: some View {
        HStack(spacing: 0) {
            modeButton(for: .ask, label: "Ask")
            modeButton(for: .act, label: "Act")
        }
        .background(OmiColors.backgroundSecondary)
        .cornerRadius(14)
    }

    private func modeButton(for targetMode: ChatMode, label: String) -> some View {
        Button(action: { mode = targetMode }) {
            Text(label)
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(mode == targetMode ? .white : OmiColors.textTertiary)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(mode == targetMode ? OmiColors.purplePrimary : Color.clear)
                .cornerRadius(12)
        }
        .buttonStyle(.plain)
    }
}
