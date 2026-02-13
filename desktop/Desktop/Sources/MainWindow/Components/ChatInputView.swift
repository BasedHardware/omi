import SwiftUI

/// Reusable chat input field with send button, extracted from ChatPage.
/// Used by both ChatPage (main chat) and TaskChatPanel (task sidebar chat).
struct ChatInputView: View {
    let onSend: (String) -> Void
    let isSending: Bool
    var placeholder: String = "Type a message..."

    @State private var inputText = ""
    @FocusState private var isInputFocused: Bool

    private var canSend: Bool {
        !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !isSending
    }

    var body: some View {
        HStack(spacing: 12) {
            TextField(placeholder, text: $inputText, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 14))
                .foregroundColor(OmiColors.textPrimary)
                .focused($isInputFocused)
                .padding(12)
                .lineLimit(1...5)
                .onSubmit {
                    sendMessage()
                }
                .frame(maxWidth: .infinity)
                .background(OmiColors.backgroundSecondary)
                .cornerRadius(20)
                .contentShape(Rectangle())
                .onTapGesture {
                    isInputFocused = true
                }

            Button(action: sendMessage) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 32))
                    .foregroundColor(canSend ? OmiColors.purplePrimary : OmiColors.textTertiary)
            }
            .buttonStyle(.plain)
            .disabled(!canSend)
        }
    }

    private func sendMessage() {
        guard canSend else { return }
        let text = inputText
        inputText = ""
        onSend(text)
    }
}
