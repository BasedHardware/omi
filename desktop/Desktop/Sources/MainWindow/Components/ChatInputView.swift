import Cocoa
import SwiftUI
import UniformTypeIdentifiers

/// A file attachment pending upload in the chat input.
struct ChatAttachment: Identifiable, Equatable {
    let id = UUID()
    let url: URL
    let filename: String
    let isImage: Bool
    let thumbnailImage: NSImage?

    static func == (lhs: ChatAttachment, rhs: ChatAttachment) -> Bool {
        lhs.id == rhs.id
    }

    init(url: URL) {
        self.url = url
        self.filename = url.lastPathComponent
        let imageExtensions: Set<String> = ["jpg", "jpeg", "png", "gif", "webp", "heic", "bmp", "tiff"]
        self.isImage = imageExtensions.contains(url.pathExtension.lowercased())
        if self.isImage, let image = NSImage(contentsOf: url) {
            self.thumbnailImage = image
        } else {
            self.thumbnailImage = nil
        }
    }
}

/// Reusable chat input field with send button.
///
/// Layout inspired by ChatGPT-style prompt input:
///   - Card container with rounded border, supports drag & drop
///   - Attachment previews above the text area
///   - Multi-line text area
///   - Bottom toolbar with + (attachments) and send button
struct ChatInputView: View {
    let onSend: (String) -> Void
    var onSendWithAttachments: ((String, [ChatAttachment]) -> Void)? = nil
    var onFollowUp: ((String) -> Void)? = nil
    var onStop: (() -> Void)? = nil
    let isSending: Bool
    var isStopping: Bool = false
    var placeholder: String = "What would you like to know?"
    @Binding var mode: ChatMode
    var pendingText: Binding<String>?
    var showToolbar: Bool = true

    @AppStorage("askModeEnabled") private var askModeEnabled = false
    @Environment(\.fontScale) private var fontScale
    @Binding var inputText: String
    @State private var attachments: [ChatAttachment] = []
    @State private var isDragOver = false

    private var hasText: Bool {
        !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var hasContent: Bool {
        hasText || !attachments.isEmpty
    }

    private let inputPaddingH: CGFloat = 16
    private let inputPaddingV: CGFloat = 14

    var body: some View {
        VStack(spacing: 0) {
            // Attachment previews
            if !attachments.isEmpty {
                attachmentPreviewBar
            }

            // Text input area
            ZStack(alignment: .topTrailing) {
                Text(inputText.isEmpty ? " " : inputText + " ")
                    .scaledFont(size: 14)
                    .padding(.horizontal, inputPaddingH)
                    .padding(.vertical, inputPaddingV)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .opacity(0)
                    .allowsHitTesting(false)
                    .accessibilityHidden(true)
                    .overlay(alignment: .topLeading) {
                        if inputText.isEmpty {
                            Text(placeholder)
                                .scaledFont(size: 14)
                                .foregroundColor(NootoColors.textTertiary)
                                .padding(.horizontal, inputPaddingH)
                                .padding(.vertical, inputPaddingV)
                                .allowsHitTesting(false)
                        }
                    }
                    .overlay {
                        NootoTextEditor(
                            text: $inputText,
                            fontSize: round(14 * fontScale),
                            textColor: NSColor(NootoColors.textPrimary),
                            textContainerInset: NSSize(width: inputPaddingH, height: inputPaddingV),
                            onSubmit: handleSubmit
                        )
                    }
                    .frame(minHeight: 60, maxHeight: 200)
                    .clipped()

                if askModeEnabled {
                    ChatModeToggle(mode: $mode)
                        .padding(.top, 10)
                        .padding(.trailing, 12)
                }
            }

            // Bottom toolbar
            HStack(spacing: 4) {
                if showToolbar {
                    // Attachments button
                    Button(action: openFilePicker) {
                        Image(systemName: "plus")
                            .scaledFont(size: 15, weight: .medium)
                            .foregroundColor(NootoColors.textSecondary)
                            .frame(width: 30, height: 30)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .help("Attach files")
                }

                Spacer()

                // Send / Stop button
                sendButton
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
        }
        .background(NootoColors.backgroundSecondary)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .overlay(
            RoundedRectangle(cornerRadius: 16)
                .stroke(isDragOver ? NootoColors.brandPrimary : NootoColors.textTertiary.opacity(0.2), lineWidth: isDragOver ? 2 : 1)
        )
        .onDrop(of: [.fileURL, .image], isTargeted: $isDragOver) { providers in
            handleDrop(providers: providers)
        }
        .fixedSize(horizontal: false, vertical: true)
        .onAppear {
            if !askModeEnabled { mode = .act }
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
            if !enabled { mode = .act }
        }
    }

    // MARK: - Attachment Previews

    private var attachmentPreviewBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(attachments) { attachment in
                    attachmentThumbnail(attachment)
                }
            }
            .padding(.horizontal, 14)
            .padding(.top, 12)
            .padding(.bottom, 4)
        }
    }

    private func attachmentThumbnail(_ attachment: ChatAttachment) -> some View {
        ZStack(alignment: .topTrailing) {
            if let thumb = attachment.thumbnailImage {
                Image(nsImage: thumb)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
                    .frame(width: 56, height: 56)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            } else {
                VStack(spacing: 4) {
                    Image(systemName: "doc.fill")
                        .scaledFont(size: 18)
                        .foregroundColor(NootoColors.textTertiary)
                    Text(attachment.url.pathExtension.uppercased())
                        .scaledFont(size: 9, weight: .semibold)
                        .foregroundColor(NootoColors.textTertiary)
                }
                .frame(width: 56, height: 56)
                .background(NootoColors.backgroundTertiary)
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }

            // Remove button
            Button {
                attachments.removeAll { $0.id == attachment.id }
            } label: {
                Image(systemName: "xmark")
                    .scaledFont(size: 8, weight: .bold)
                    .foregroundColor(.white)
                    .frame(width: 16, height: 16)
                    .background(Color.black.opacity(0.6))
                    .clipShape(Circle())
            }
            .buttonStyle(.plain)
            .offset(x: 4, y: -4)
        }
    }

    // MARK: - Send Button

    @ViewBuilder
    private var sendButton: some View {
        if isSending && !hasContent {
            if isStopping {
                ProgressView()
                    .controlSize(.small)
                    .frame(width: 30, height: 30)
            } else {
                Button(action: { onStop?() }) {
                    Image(systemName: "stop.fill")
                        .scaledFont(size: 12)
                        .foregroundColor(.white)
                        .frame(width: 30, height: 30)
                        .background(Color.red.opacity(0.8))
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
            }
        } else {
            Button(action: handleSubmit) {
                Image(systemName: "arrow.turn.down.left")
                    .scaledFont(size: 13, weight: .semibold)
                    .foregroundColor(hasContent ? .white : NootoColors.textTertiary)
                    .frame(width: 30, height: 30)
                    .background(hasContent ? NootoColors.brandPrimary : NootoColors.backgroundTertiary)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            .buttonStyle(.plain)
            .disabled(!hasContent)
        }
    }

    // MARK: - File Picker

    private func openFilePicker() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.allowedContentTypes = [
            .image, .pdf,
            UTType(filenameExtension: "doc")!, UTType(filenameExtension: "docx")!,
            UTType(filenameExtension: "txt")!, UTType(filenameExtension: "csv")!,
            UTType(filenameExtension: "xls")!, UTType(filenameExtension: "xlsx")!,
        ].compactMap { $0 }
        panel.begin { response in
            if response == .OK {
                let newAttachments = panel.urls.map { ChatAttachment(url: $0) }
                DispatchQueue.main.async {
                    attachments.append(contentsOf: newAttachments)
                }
            }
        }
    }

    // MARK: - Drag & Drop

    private func handleDrop(providers: [NSItemProvider]) -> Bool {
        var handled = false
        for provider in providers {
            if provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { data, _ in
                    guard let data = data as? Data,
                          let url = URL(dataRepresentation: data, relativeTo: nil) else { return }
                    DispatchQueue.main.async {
                        attachments.append(ChatAttachment(url: url))
                    }
                }
                handled = true
            } else if provider.hasItemConformingToTypeIdentifier(UTType.image.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.image.identifier, options: nil) { data, _ in
                    var imageURL: URL?
                    if let url = data as? URL {
                        imageURL = url
                    } else if let data = data as? Data {
                        let tmp = FileManager.default.temporaryDirectory.appendingPathComponent("dropped-\(UUID().uuidString).png")
                        try? data.write(to: tmp)
                        imageURL = tmp
                    }
                    if let url = imageURL {
                        DispatchQueue.main.async {
                            attachments.append(ChatAttachment(url: url))
                        }
                    }
                }
                handled = true
            }
        }
        return handled
    }

    // MARK: - Submit

    private func handleSubmit() {
        guard hasContent else { return }
        let text = inputText
        let files = attachments
        inputText = ""
        attachments = []
        if isSending {
            onFollowUp?(text)
        } else if !files.isEmpty, let sendWithFiles = onSendWithAttachments {
            sendWithFiles(text, files)
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
        .background(NootoColors.backgroundSecondary)
        .cornerRadius(14)
    }

    private func modeButton(for targetMode: ChatMode, label: String) -> some View {
        Button(action: { mode = targetMode }) {
            Text(label)
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(mode == targetMode ? .white : NootoColors.textTertiary)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(mode == targetMode ? NootoColors.brandPrimary : Color.clear)
                .cornerRadius(12)
        }
        .buttonStyle(.plain)
    }
}
