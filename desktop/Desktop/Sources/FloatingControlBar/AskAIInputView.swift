import SwiftUI

/// "Ask a question..." input panel for the floating control bar.
struct AskAIInputView: View {
    @Binding var userInput: String
    @Binding var screenshotURL: URL?
    @State private var localInput: String = ""
    @State private var textHeight: CGFloat = 40

    var onSend: ((String) -> Void)?
    var onCancel: (() -> Void)?
    var onHeightChange: ((CGFloat) -> Void)?
    var onCaptureScreenshot: (() -> Void)?

    private let minHeight: CGFloat = 40
    private let maxHeight: CGFloat = 200

    var body: some View {
        VStack(spacing: 0) {
            // Escape hint
            HStack {
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
                .padding(.top, 8)
                .padding(.trailing, 16)
            }

            // Screenshot thumbnail
            if let url = screenshotURL, let nsImage = NSImage(contentsOf: url) {
                HStack(spacing: 8) {
                    ZStack(alignment: .topTrailing) {
                        Image(nsImage: nsImage)
                            .resizable()
                            .aspectRatio(contentMode: .fill)
                            .frame(width: 80, height: 50)
                            .cornerRadius(8)
                            .clipped()

                        Button(action: { screenshotURL = nil }) {
                            Image(systemName: "xmark.circle.fill")
                                .scaledFont(size: 14)
                                .foregroundColor(.white)
                                .shadow(radius: 2)
                        }
                        .buttonStyle(.plain)
                        .offset(x: 4, y: -4)
                    }
                    Text("Screenshot attached")
                        .scaledFont(size: 11)
                        .foregroundColor(.secondary)
                    Spacer()

                    Button(action: { onCaptureScreenshot?() }) {
                        Image(systemName: "arrow.clockwise")
                            .scaledFont(size: 12)
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help("Retake screenshot")
                }
                .padding(.horizontal, 16)
                .padding(.top, 6)
            }

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
}
