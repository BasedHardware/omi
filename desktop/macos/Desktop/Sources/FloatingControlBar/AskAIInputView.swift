import SwiftUI

/// "Ask a question..." input panel for the floating control bar.
struct AskAIInputView: View {
    @EnvironmentObject var state: FloatingControlBarState
    @Binding var userInput: String
    @State private var localInput: String = ""
    @State private var textHeight: CGFloat = 40
    @State private var hasMarkedText = false

    var canClearVisibleConversation: Bool = false
    var onSend: ((String) -> Void)?
    var onClearVisibleConversation: (() -> Void)?
    var onEscape: (() -> Void)?
    var onHeightChange: ((CGFloat) -> Void)?

    private let minHeight: CGFloat = 40
    private let maxHeight: CGFloat = 200
    private var trimmedInput: String { localInput.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var canSend: Bool { !hasMarkedText && !trimmedInput.isEmpty }

    var body: some View {
        VStack(spacing: 0) {
            if canClearVisibleConversation {
                HStack {
                    Spacer()

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
                .padding(.top, 8)
                .padding(.trailing, 16)
            }

            HStack(spacing: 6) {
                ZStack(alignment: .topLeading) {
                    if localInput.isEmpty && !hasMarkedText {
                        Text("Ask a question...")
                            .scaledFont(size: 13)
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 8)
                    }

                    OmiTextEditor(
                        text: $localInput,
                        lineFragmentPadding: 8,
                        onSubmit: {
                            guard canSend else { return }
                            onSend?(trimmedInput)
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
                    .onChange(of: localInput) { _, newValue in
                        userInput = newValue
                    }
                    .onAppear {
                        localInput = userInput
                    }
                }
                .padding(.horizontal, 4)
                .frame(height: textHeight)

                Button(action: {
                    guard canSend else { return }
                    onSend?(trimmedInput)
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
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity)
        }
        .onExitCommand {
            onEscape?()
        }
    }

    // Model picker moved to Settings > Ask Omi Floating Bar
    // private var modelPicker: some View { ... }
    // private func showModelMenu() { ... }
    // private var currentModelLabel: String { ... }
}
