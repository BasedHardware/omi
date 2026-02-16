import SwiftUI

/// "Ask a question..." input panel for the floating control bar.
struct AskAIInputView: View {
    @EnvironmentObject var state: FloatingControlBarState
    @Binding var userInput: String
    @State private var localInput: String = ""
    @State private var textHeight: CGFloat = 40

    var onSend: ((String) -> Void)?
    var onCancel: (() -> Void)?
    var onHeightChange: ((CGFloat) -> Void)?

    private let minHeight: CGFloat = 40
    private let maxHeight: CGFloat = 200

    var body: some View {
        VStack(spacing: 0) {
            // Top bar: model picker + escape hint
            HStack {
                // Model picker
                modelPicker
                    .padding(.leading, 16)

                Spacer()

                HStack(spacing: 4) {
                    Text("esc")
                        .scaledFont(size: 11)
                        .foregroundColor(.secondary)
                        .frame(width: 30, height: 16)
                        .background(Color.white.opacity(0.1))
                        .cornerRadius(4)
                    Text("to close")
                        .scaledFont(size: 11)
                        .foregroundColor(.secondary)
                }
                .padding(.trailing, 16)
            }
            .padding(.top, 8)

            HStack(spacing: 6) {
                ZStack(alignment: .topLeading) {
                    if localInput.isEmpty {
                        Text("Ask a question...")
                            .scaledFont(size: 13)
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 8)
                    }

                    ResizableTextEditor(
                        text: $localInput,
                        minHeight: minHeight,
                        maxHeight: maxHeight,
                        onHeightChange: { newHeight in
                            if abs(textHeight - newHeight) > 1 {
                                textHeight = newHeight
                                onHeightChange?(newHeight)
                            }
                        },
                        onSubmit: {
                            let trimmed = localInput.trimmingCharacters(in: .whitespacesAndNewlines)
                            guard !trimmed.isEmpty else { return }
                            onSend?(trimmed)
                        },
                        focusOnAppear: true
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
                    let trimmed = localInput.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !trimmed.isEmpty else { return }
                    onSend?(trimmed)
                }) {
                    Image(systemName: "arrow.up.circle.fill")
                        .scaledFont(size: 24)
                        .foregroundColor(
                            localInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                ? .secondary : .white
                        )
                }
                .disabled(localInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity)
        }
        .onExitCommand {
            onCancel?()
        }
    }

    private var modelPicker: some View {
        Menu {
            ForEach(FloatingControlBarState.availableModels, id: \.id) { model in
                Button(action: { state.selectedModel = model.id }) {
                    HStack {
                        Text(model.label)
                        if state.selectedModel == model.id {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Text(currentModelLabel)
                    .scaledFont(size: 11)
                    .foregroundColor(.secondary)
                Image(systemName: "chevron.up.chevron.down")
                    .scaledFont(size: 8)
                    .foregroundColor(.secondary)
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(Color.white.opacity(0.1))
            .cornerRadius(4)
        }
        .menuStyle(.borderlessButton)
        .fixedSize()
    }

    private var currentModelLabel: String {
        FloatingControlBarState.availableModels.first { $0.id == state.selectedModel }?.label ?? "Sonnet"
    }
}
