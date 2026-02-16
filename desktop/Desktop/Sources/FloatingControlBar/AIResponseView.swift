import MarkdownUI
import SwiftUI

/// Streaming markdown response view for the floating control bar.
struct AIResponseView: View {
    @Binding var isLoading: Bool
    @Binding var responseText: String
    @State private var isQuestionExpanded = false
    @State private var followUpText: String = ""

    let userInput: String

    var onClose: (() -> Void)?
    var onSendFollowUp: ((String) -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            headerView
                .fixedSize(horizontal: false, vertical: true)
            questionBar
            contentView
            if !isLoading {
                followUpInputView
            }
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
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

    private var followUpInputView: some View {
        HStack(spacing: 6) {
            TextField("Ask follow up...", text: $followUpText)
                .textFieldStyle(.plain)
                .scaledFont(size: 13)
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(Color.white.opacity(0.1))
                .cornerRadius(8)
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

    private var contentView: some View {
        Group {
            if isLoading {
                Spacer()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    Markdown(responseText)
                        .scaledMarkdownTheme(.ai)
                        .textSelection(.enabled)
                        .environment(\.colorScheme, .dark)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 8)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
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
}
