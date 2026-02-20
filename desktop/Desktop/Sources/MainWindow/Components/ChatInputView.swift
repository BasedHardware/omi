import Cocoa
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
    var isStopping: Bool = false
    var placeholder: String = "Type a message..."
    @Binding var mode: ChatMode
    /// Optional text to pre-fill the input (e.g. task context). Consumed on change.
    var pendingText: Binding<String>?

    @AppStorage("askModeEnabled") private var askModeEnabled = false
    @Environment(\.fontScale) private var fontScale
    @Binding var inputText: String

    private var hasText: Bool {
        !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    /// Padding used for both the NSTextView (via textContainerInset) and the
    /// placeholder overlay — guaranteeing the cursor and placeholder align.
    private let inputPaddingH: CGFloat = 12
    private let inputPaddingV: CGFloat = 12

    var body: some View {
        HStack(alignment: .bottom, spacing: 8) {
            // Input field with floating toggle
            ZStack(alignment: .topTrailing) {
                // Input field — NSTextView with auto-grow height
                ZStack(alignment: .topLeading) {
                    // Hidden text to calculate content height (drives ZStack size)
                    Text(inputText.isEmpty ? " " : inputText + " ")
                        .scaledFont(size: 14)
                        .padding(.horizontal, inputPaddingH)
                        .padding(.vertical, inputPaddingV)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .opacity(0)
                        .allowsHitTesting(false)
                        .accessibilityHidden(true)

                    // Placeholder text — padding matches textContainerInset exactly
                    if inputText.isEmpty {
                        Text(placeholder)
                            .scaledFont(size: 14)
                            .foregroundColor(OmiColors.textTertiary)
                            .padding(.horizontal, inputPaddingH)
                            .padding(.vertical, inputPaddingV)
                            .allowsHitTesting(false)
                    }

                    // NSTextView with lineFragmentPadding=0 and explicit textContainerInset
                    // so cursor position is deterministic and matches placeholder exactly
                    OmiTextEditor(
                        text: $inputText,
                        fontSize: round(14 * fontScale),
                        textColor: NSColor(OmiColors.textPrimary),
                        textContainerInset: NSSize(width: inputPaddingH, height: inputPaddingV),
                        onSubmit: handleSubmit
                    )
                    .frame(minHeight: 0, maxHeight: .infinity)
                }
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxHeight: 200)
                .background(OmiColors.backgroundSecondary)
                .cornerRadius(12)

                // Floating Ask/Act toggle (top-right, inside the input area)
                if askModeEnabled {
                    ChatModeToggle(mode: $mode)
                        .padding(.top, 8)
                        .padding(.trailing, 8)
                }
            }

            // Send/Stop button — inline to the right of the input
            if isSending && !hasText {
                if isStopping {
                    ProgressView()
                        .controlSize(.small)
                        .frame(width: 24, height: 24)
                } else {
                    Button(action: { onStop?() }) {
                        Image(systemName: "stop.circle.fill")
                            .scaledFont(size: 24)
                            .foregroundColor(.red.opacity(0.8))
                    }
                    .buttonStyle(.plain)
                }
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
        .onAppear {
            // When ask mode is disabled, ensure we're always in act mode
            if !askModeEnabled {
                mode = .act
            }
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
        .onChange(of: askModeEnabled) { _, enabled in
            if !enabled {
                mode = .act
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
