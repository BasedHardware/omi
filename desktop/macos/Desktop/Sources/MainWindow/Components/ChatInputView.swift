import AppKit
import Cocoa
import SwiftUI
import UniformTypeIdentifiers

/// Reusable chat input field with send button, extracted from ChatPage.
/// Used by both ChatPage (main chat) and TaskChatPanel (task sidebar chat).
///
/// When `isSending` is true:
///   - Input stays enabled so the user can type a follow-up
///   - If input is empty, the button becomes a stop button
///   - If input has text, pressing send calls `onFollowUp` (redirects the agent)
///
/// Attachment support is opt-in: pass `attachments`, `onAttachmentsAdded`, and
/// `onAttachmentRemoved` to enable the paperclip button, the staged-files row,
/// and drag-drop. When omitted (e.g. task-sidebar chat) the input behaves as
/// before.
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
    @Binding var inputText: String

    /// Currently staged attachments. When nil, the attach button + drag-drop are hidden.
    var attachments: Binding<[ChatAttachment]>? = nil
    /// Called when the user picks files via the paperclip or drags them onto the input.
    var onAttachmentsAdded: (([URL]) -> Void)? = nil
    /// Called when the user removes a staged attachment chip.
    var onAttachmentRemoved: ((String) -> Void)? = nil

    @AppStorage("askModeEnabled") private var askModeEnabled = false
    @Environment(\.fontScale) private var fontScale
    @State private var isDropTargeted = false
    @State private var hasMarkedText = false

    private var hasText: Bool {
        !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private var attachmentsEnabled: Bool { attachments != nil }
    private var currentAttachments: [ChatAttachment] { attachments?.wrappedValue ?? [] }

    /// Padding used for both the NSTextView (via textContainerInset) and the
    /// placeholder overlay — guaranteeing the cursor and placeholder align.
    private let inputPaddingH: CGFloat = 12
    private let inputPaddingV: CGFloat = 12

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if attachmentsEnabled && !currentAttachments.isEmpty {
                AttachmentPreviewRow(
                    attachments: currentAttachments,
                    onRemove: { id in onAttachmentRemoved?(id) }
                )
            }

            HStack(alignment: .bottom, spacing: 8) {
                if attachmentsEnabled {
                    Button(action: pickFiles) {
                        Image(systemName: "paperclip")
                            .scaledFont(size: 18, weight: .medium)
                            .foregroundColor(OmiColors.textTertiary)
                            .frame(width: 32, height: 32)
                    }
                    .buttonStyle(.plain)
                    .help("Attach files")
                    .disabled(currentAttachments.count >= kMaxChatAttachments)
                }

                // Input field with floating toggle
                ZStack(alignment: .topTrailing) {
                    // Hidden Text drives the SwiftUI height; OmiTextEditor overlays it exactly.
                    // This lets SwiftUI measure height from text content without fighting AppKit's
                    // scroll view layout — the onHeightChange pattern caused layout loops inside
                    // the TaskChatPanel VStack with frame(maxHeight: .infinity).
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
                            // Placeholder text — padding matches textContainerInset exactly
                            if inputText.isEmpty && !hasMarkedText {
                                Text(placeholder)
                                    .scaledFont(size: 14)
                                    .foregroundColor(OmiColors.textTertiary)
                                    .padding(.horizontal, inputPaddingH)
                                    .padding(.vertical, inputPaddingV)
                                    .allowsHitTesting(false)
                            }
                        }
                        .overlay {
                            OmiTextEditor(
                                text: $inputText,
                                fontSize: round(14 * fontScale),
                                textColor: NSColor(OmiColors.textPrimary),
                                textContainerInset: NSSize(width: inputPaddingH, height: inputPaddingV),
                                onSubmit: handleSubmit,
                                onMarkedTextChange: { hasMarkedText = $0 }
                            )
                        }
                        .frame(maxHeight: 200)
                        .clipped()
                        .background(OmiColors.backgroundTertiary)
                        .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))

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
                            .foregroundColor(canSend ? OmiColors.purplePrimary : OmiColors.textQuaternary)
                    }
                    .buttonStyle(.plain)
                    .disabled(!canSend)
                }
            }
        }
        .padding(12)
        .omiPanel(fill: OmiColors.backgroundSecondary, radius: 22, stroke: dropStrokeColor, shadowOpacity: 0.1, shadowRadius: 12, shadowY: 6)
        .fixedSize(horizontal: false, vertical: true)
        .if(attachmentsEnabled) { view in
            view.onDrop(of: [UTType.fileURL], isTargeted: $isDropTargeted, perform: handleDrop)
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

    /// Send is enabled when there's text OR (when supported) any attachment ready
    /// to ship — Flutter allows sending attachments without text.
    private var canSend: Bool {
        guard !hasMarkedText else { return false }
        if hasText { return true }
        if attachmentsEnabled && !currentAttachments.isEmpty { return true }
        return false
    }

    private var dropStrokeColor: Color {
        isDropTargeted ? OmiColors.purplePrimary.opacity(0.6) : OmiColors.border.opacity(0.2)
    }

    private func handleSubmit() {
        guard canSend else { return }
        let text = inputText
        inputText = ""
        if isSending {
            onFollowUp?(text)
        } else {
            onSend(text)
        }
    }

    private func pickFiles() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [
            .image, .jpeg, .png, .gif, .heic, .heif, .webP, .tiff, .bmp,
            .pdf, .plainText, .json, .commaSeparatedText, .html,
            .text, .content,
        ]
        if panel.runModal() == .OK {
            let remaining = max(0, kMaxChatAttachments - currentAttachments.count)
            let urls = Array(panel.urls.prefix(remaining))
            if !urls.isEmpty {
                onAttachmentsAdded?(urls)
            }
        }
    }

    private func handleDrop(providers: [NSItemProvider]) -> Bool {
        var urls: [URL] = []
        let group = DispatchGroup()
        for provider in providers {
            guard provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) else {
                continue
            }
            group.enter()
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                defer { group.leave() }
                if let data = item as? Data,
                    let url = URL(dataRepresentation: data, relativeTo: nil)
                {
                    urls.append(url)
                } else if let url = item as? URL {
                    urls.append(url)
                }
            }
        }
        // We can't make handleDrop async, so dispatch the callback once gathered.
        group.notify(queue: .main) { [urls] in
            guard !urls.isEmpty else { return }
            let remaining = max(0, kMaxChatAttachments - currentAttachments.count)
            let allowed = Array(urls.prefix(remaining))
            if !allowed.isEmpty {
                onAttachmentsAdded?(allowed)
            }
        }
        return !providers.isEmpty
    }
}

// MARK: - Attachment Preview Row

/// Horizontal row of chip-like previews shown above the input while files are
/// staged for the next send. Images show their thumbnail; other files show a
/// document icon + filename. A small "x" removes the chip.
struct AttachmentPreviewRow: View {
    let attachments: [ChatAttachment]
    let onRemove: (String) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(attachments) { attachment in
                    AttachmentChip(attachment: attachment, onRemove: { onRemove(attachment.id) })
                }
            }
            .padding(.horizontal, 2)
            .padding(.vertical, 2)
        }
        .frame(maxHeight: 80)
    }
}

private struct AttachmentChip: View {
    let attachment: ChatAttachment
    let onRemove: () -> Void
    @State private var hovering = false

    var body: some View {
        ZStack(alignment: .topTrailing) {
            HStack(spacing: 8) {
                thumbnail
                if !attachment.isImage {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(attachment.fileName)
                            .scaledFont(size: 12, weight: .medium)
                            .foregroundColor(OmiColors.textPrimary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                        Text(attachment.mimeType)
                            .scaledFont(size: 10)
                            .foregroundColor(OmiColors.textTertiary)
                            .lineLimit(1)
                    }
                    .frame(maxWidth: 160, alignment: .leading)
                }
            }
            .padding(.horizontal, attachment.isImage ? 0 : 8)
            .padding(.vertical, attachment.isImage ? 0 : 6)
            .background(OmiColors.backgroundTertiary.opacity(attachment.isImage ? 0 : 0.9))
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(alignment: .bottom) {
                if case .failed = attachment.state {
                    Text("Failed")
                        .scaledFont(size: 9, weight: .semibold)
                        .foregroundColor(.white)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 1)
                        .background(Color.red.opacity(0.85))
                        .clipShape(Capsule())
                        .padding(2)
                } else if case .uploading = attachment.state {
                    ProgressView()
                        .controlSize(.mini)
                        .padding(2)
                }
            }

            Button(action: onRemove) {
                Image(systemName: "xmark.circle.fill")
                    .scaledFont(size: 14)
                    .symbolRenderingMode(.palette)
                    .foregroundStyle(.white, Color.black.opacity(0.75))
            }
            .buttonStyle(.plain)
            .offset(x: 4, y: -4)
            .opacity(hovering ? 1.0 : 0.85)
        }
        .onHover { hovering = $0 }
    }

    @ViewBuilder
    private var thumbnail: some View {
        if attachment.isImage, let data = attachment.data, let nsImage = NSImage(data: data) {
            Image(nsImage: nsImage)
                .resizable()
                .scaledToFill()
                .frame(width: 60, height: 60)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        } else if attachment.isImage, let urlString = attachment.thumbnailURL,
            let url = URL(string: urlString)
        {
            AsyncImage(url: url) { phase in
                switch phase {
                case .success(let image):
                    image.resizable().scaledToFill()
                default:
                    Color.gray.opacity(0.2)
                }
            }
            .frame(width: 60, height: 60)
            .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        } else {
            ZStack {
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .fill(OmiColors.backgroundQuaternary.opacity(0.7))
                Image(systemName: documentIcon)
                    .scaledFont(size: 22)
                    .foregroundColor(OmiColors.textSecondary)
            }
            .frame(width: 44, height: 44)
        }
    }

    private var documentIcon: String {
        switch attachment.mimeType {
        case "application/pdf": return "doc.richtext"
        case let m where m.hasPrefix("text/"): return "doc.text"
        case "application/json": return "curlybraces"
        case let m where m.contains("spreadsheet") || m.contains("excel"): return "tablecells"
        case let m where m.contains("word"): return "doc"
        case "application/zip": return "doc.zipper"
        default: return "doc"
        }
    }
}

// MARK: - View helpers

extension View {
    /// Conditionally apply a view modifier. Keeps drag-drop opt-in so callers
    /// without an `attachments` binding don't accidentally accept files.
    @ViewBuilder
    fileprivate func `if`<Content: View>(
        _ condition: Bool, transform: (Self) -> Content
    ) -> some View {
        if condition {
            transform(self)
        } else {
            self
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
        .background(OmiColors.backgroundQuaternary.opacity(0.7))
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
    }

    private func modeButton(for targetMode: ChatMode, label: String) -> some View {
        Button(action: { mode = targetMode }) {
            Text(label)
                .scaledFont(size: 12, weight: .medium)
                .foregroundColor(mode == targetMode ? .white : OmiColors.textTertiary)
                .padding(.horizontal, 10)
                .padding(.vertical, 5)
                .background(mode == targetMode ? OmiColors.userBubble : Color.clear)
                .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}
