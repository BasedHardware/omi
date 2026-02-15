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
    /// Optional text to pre-fill the input (e.g. task context). Consumed on change.
    var pendingText: Binding<String>?

    @State private var inputText = ""
    @FocusState private var isInputFocused: Bool

    private var hasText: Bool {
        !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    var body: some View {
        VStack(spacing: 6) {
            // Controls row: Ask/Act toggle + Send/Stop button, right-aligned
            HStack(spacing: 8) {
                Spacer()

                ChatModeToggle(mode: $mode)

                if isSending && !hasText {
                    Button(action: { onStop?() }) {
                        Image(systemName: "stop.circle.fill")
                            .scaledFont(size: 24)
                            .foregroundColor(.red.opacity(0.8))
                    }
                    .buttonStyle(.plain)
                } else {
                    Button(action: handleSubmit) {
                        Image(systemName: "arrow.up.circle.fill")
                            .scaledFont(size: 24)
                            .foregroundColor(hasText ? OmiColors.purplePrimary : OmiColors.textTertiary)
                    }
                    .buttonStyle(.plain)
                    .disabled(!hasText)
                }
            }

            // Input field — TextEditor with auto-grow height
            ZStack(alignment: .topLeading) {
                // Hidden text to calculate content height (drives ZStack size)
                Text(inputText.isEmpty ? " " : inputText + " ")
                    .scaledFont(size: 14)
                    .padding(.horizontal, 17)
                    .padding(.vertical, 12)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .opacity(0)
                    .accessibilityHidden(true)

                // Placeholder text
                if inputText.isEmpty {
                    Text(placeholder)
                        .scaledFont(size: 14)
                        .foregroundColor(OmiColors.textTertiary)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 12)
                        .allowsHitTesting(false)
                }

                TextEditor(text: $inputText)
                    .scaledFont(size: 14)
                    .foregroundColor(OmiColors.textPrimary)
                    .focused($isInputFocused)
                    .scrollContentBackground(.hidden)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .frame(minHeight: 0, maxHeight: .infinity)
                    .onKeyPress(keys: [.return], phases: .down) { keyPress in
                        if keyPress.modifiers.contains(.shift) {
                            return .ignored // Shift+Enter: newline
                        }
                        handleSubmit()
                        return .handled // Enter: send
                    }
            }
            .frame(maxHeight: 200)
            .fixedSize(horizontal: false, vertical: true)
            .background(OmiColors.backgroundSecondary)
            .cornerRadius(12)
            .contentShape(Rectangle())
            .onTapGesture {
                isInputFocused = true
            }
            .onAppear {
                isInputFocused = true
                if let pending = pendingText?.wrappedValue, !pending.isEmpty {
                    inputText = pending
                    pendingText?.wrappedValue = ""
                }
            }
            .onChange(of: pendingText?.wrappedValue ?? "") { _, newValue in
                if !newValue.isEmpty {
                    inputText = newValue
                    pendingText?.wrappedValue = ""
                }
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
