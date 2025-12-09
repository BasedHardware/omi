import Cocoa
import Combine
import MarkdownUI
import SwiftUI

// MARK: - Notification Names
extension Notification.Name {
    static let dragDidStart = Notification.Name("dragDidStart")
    static let dragDidEnd = Notification.Name("dragDidEnd")
}

// MARK: - Selectable Text View
private struct SelectableText: NSViewRepresentable {
    let text: String
    let font: NSFont
    let textColor: NSColor
    let maxHeight: CGFloat?

    init(text: String, font: NSFont, textColor: NSColor, maxHeight: CGFloat? = nil) {
        self.text = text
        self.font = font
        self.textColor = textColor
        self.maxHeight = maxHeight
    }

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSTextView.scrollableTextView()
        guard let textView = scrollView.documentView as? NSTextView else {
            return scrollView
        }

        textView.isEditable = false
        textView.isSelectable = true
        textView.drawsBackground = false
        textView.backgroundColor = .clear
        textView.font = font
        textView.textColor = textColor
        textView.textContainerInset = NSSize(width: 0, height: 4)
        textView.textContainer?.lineFragmentPadding = 0
        textView.textContainer?.widthTracksTextView = true

        // Enable vertical scrolling if maxHeight is set
        scrollView.hasVerticalScroller = maxHeight != nil
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.backgroundColor = .clear
        scrollView.drawsBackground = false
        scrollView.borderType = .noBorder

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? NSTextView else { return }
        if textView.string != text {
            textView.string = text
        }
        textView.font = font
        textView.textColor = textColor
    }
}

// MARK: - Draggable Area View
private struct DraggableAreaView: NSViewRepresentable {
    let targetWindow: NSWindow?

    func makeNSView(context: Context) -> NSView {
        let view = DraggableNSView()
        view.targetWindow = targetWindow
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {}

    class DraggableNSView: NSView {
        weak var targetWindow: NSWindow?
        private var initialLocation: NSPoint?

        override func mouseDown(with event: NSEvent) {
            initialLocation = event.locationInWindow
            NotificationCenter.default.post(name: .dragDidStart, object: nil)
        }

        override func mouseUp(with event: NSEvent) {
            super.mouseUp(with: event)
            NotificationCenter.default.post(name: .dragDidEnd, object: nil)
            initialLocation = nil
        }

        override func mouseDragged(with event: NSEvent) {
            guard let targetWindow = targetWindow, let initialLocation = initialLocation else {
                return
            }

            let currentLocation = event.locationInWindow
            let newOrigin = NSPoint(
                x: targetWindow.frame.origin.x + (currentLocation.x - initialLocation.x),
                y: targetWindow.frame.origin.y + (currentLocation.y - initialLocation.y)
            )

            // Disable implicit animations during drag
            NSAnimationContext.beginGrouping()
            NSAnimationContext.current.duration = 0
            targetWindow.setFrameOrigin(newOrigin)
            NSAnimationContext.endGrouping()
        }
    }
}

// MARK: - Resizable Text Editor
private struct ResizableTextEditor: NSViewRepresentable {
    @Binding var text: String
    let minHeight: CGFloat
    let maxHeight: CGFloat
    let onHeightChange: (CGFloat) -> Void

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSTextView.scrollableTextView()
        guard let textView = scrollView.documentView as? NSTextView else {
            return scrollView
        }

        textView.font = .systemFont(ofSize: 13)
        textView.textColor = .labelColor  // Adaptive: white in dark mode, black in light mode
        textView.backgroundColor = .clear
        textView.drawsBackground = false
        textView.isRichText = false
        textView.allowsUndo = true
        textView.isAutomaticQuoteSubstitutionEnabled = false
        textView.isAutomaticDashSubstitutionEnabled = false
        textView.isAutomaticTextReplacementEnabled = false
        textView.delegate = context.coordinator

        // Configure text container
        textView.textContainer?.lineFragmentPadding = 8
        textView.textContainerInset = NSSize(width: 0, height: 8)
        textView.textContainer?.widthTracksTextView = true

        // Configure scroll view
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.backgroundColor = .clear
        scrollView.drawsBackground = false

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? NSTextView else { return }

        if textView.string != text {
            textView.string = text
            context.coordinator.updateHeight(for: textView, scrollView: scrollView)
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(
            text: $text,
            minHeight: minHeight,
            maxHeight: maxHeight,
            onHeightChange: onHeightChange
        )
    }

    class Coordinator: NSObject, NSTextViewDelegate {
        @Binding var text: String
        let minHeight: CGFloat
        let maxHeight: CGFloat
        let onHeightChange: (CGFloat) -> Void
        private var lastHeight: CGFloat = 0

        init(
            text: Binding<String>, minHeight: CGFloat, maxHeight: CGFloat,
            onHeightChange: @escaping (CGFloat) -> Void
        ) {
            self._text = text
            self.minHeight = minHeight
            self.maxHeight = maxHeight
            self.onHeightChange = onHeightChange
        }

        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else { return }

            // Update text immediately without async
            self.text = textView.string

            // Calculate height synchronously
            if let scrollView = textView.enclosingScrollView {
                self.updateHeight(for: textView, scrollView: scrollView)
            }
        }

        func updateHeight(for textView: NSTextView, scrollView: NSScrollView) {
            guard let layoutManager = textView.layoutManager,
                let textContainer = textView.textContainer
            else { return }

            layoutManager.ensureLayout(for: textContainer)
            let usedRect = layoutManager.usedRect(for: textContainer)
            let contentHeight = usedRect.height + textView.textContainerInset.height * 2
            let constrainedHeight = min(max(contentHeight, minHeight), maxHeight)

            // Only notify if height changed by more than 1pt
            if abs(constrainedHeight - lastHeight) > 1 {
                lastHeight = constrainedHeight
                onHeightChange(constrainedHeight)
            }
        }
    }
}

// MARK: - State Management
/// Observable object to hold the state for the floating control bar.
private class FloatingControlBarState: ObservableObject {
    @Published var isRecording: Bool = false
    @Published var isPaused: Bool = false
    @Published var duration: Int = 0
    @Published var isInitialising: Bool = false
    @Published var isDragging: Bool = false

    // AI conversation state
    @Published var showingAIConversation: Bool = false
    @Published var showingAIResponse: Bool = false
    @Published var isAILoading: Bool = true
    @Published var aiInputText: String = ""
    @Published var aiResponseText: String = ""
    @Published var displayedQuery: String = ""
    @Published var fileUrl: URL?
    @Published var inputViewHeight: CGFloat = 120  // Initial minimum height: 60 (control) + 40 (input)

    // Shortcut recording state
    @Published var isRecordingShortcut: Bool = false
    @Published var recordedKeyCode: Int?
    @Published var recordedModifiers: UInt32?
    @Published var shortcutRecordingError: String?

    // Current shortcut display
    @Published var currentShortcutKeys: [String] = ["⌘", "↩︎"]
}

// MARK: - AI Input View
private struct AskAIInputView: View {
    @Binding var userInput: String
    @State private var localInput: String = ""
    @State private var textHeight: CGFloat = 40
    @FocusState private var isInputFocused: Bool
    let fileUrl: URL?

    var onSend: ((String, URL?) -> Void)?
    var onRemoveScreenshot: (() -> Void)?
    var onCaptureScreenshot: (() -> Void)?
    var onSelectFile: (() -> Void)?
    var onCancel: (() -> Void)?
    var onHeightChange: ((CGFloat) -> Void)?

    private let minHeight: CGFloat = 40  // Minimum height for 1 line
    private let maxHeight: CGFloat = 200  // Maximum height

    init(
        userInput: Binding<String>,
        fileUrl: URL?,
        onSend: ((String, URL?) -> Void)? = nil,
        onRemoveScreenshot: (() -> Void)? = nil,
        onCaptureScreenshot: (() -> Void)? = nil,
        onSelectFile: (() -> Void)? = nil,
        onCancel: (() -> Void)? = nil,
        onHeightChange: ((CGFloat) -> Void)? = nil
    ) {
        self._userInput = userInput
        self.fileUrl = fileUrl
        self.onSend = onSend
        self.onRemoveScreenshot = onRemoveScreenshot
        self.onCaptureScreenshot = onCaptureScreenshot
        self.onSelectFile = onSelectFile
        self.onCancel = onCancel
        self.onHeightChange = onHeightChange
    }

    var body: some View {
        VStack(spacing: 0) {
            // Hint at top
            HStack {
                Spacer()
                HStack(spacing: 4) {
                    Text("esc")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                        .frame(width: 30, height: 16)
                        .background(Color.primary.opacity(0.1))
                        .cornerRadius(4)
                    Text("to close")
                        .font(.system(size: 11))
                        .foregroundColor(.secondary)
                }
                .padding(.top, 8)
                .padding(.trailing, 16)
            }

            HStack(spacing: 6) {
                // File preview or capture/select buttons
                if let url = fileUrl {
                    filePreviewView(url: url)
                } else {
                    // Quick capture button
                    Button(action: { onCaptureScreenshot?() }) {
                        Image(systemName: "camera.fill")
                            .font(.system(size: 16))
                            .foregroundColor(.secondary)
                            .frame(width: 32, height: 32)
                            .background(Color.primary.opacity(0.1))
                            .cornerRadius(8)
                    }
                    .buttonStyle(.plain)
                    .help("Capture")
                }

                // Dropdown menu - always visible
                Menu("") {
                    Button(action: { onCaptureScreenshot?() }) {
                        Label("Capture", systemImage: "camera.fill")
                    }
                    Button(action: { onSelectFile?() }) {
                        Label("Browse Files...", systemImage: "photo.on.rectangle")
                    }
                }
                .menuStyle(.borderlessButton)
                .frame(width: 20)
                .help("Attach file")

                ZStack(alignment: .topLeading) {
                    if localInput.isEmpty {
                        Text("Ask a question...")
                            .font(.system(size: 13))
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
                        }
                    )
                    .focused($isInputFocused)
                    .onChange(of: localInput) {
                        userInput = $0
                    }
                    .onAppear {
                        localInput = userInput
                        isInputFocused = true
                    }
                }
                .padding(.horizontal, 4)
                .frame(height: textHeight)

                Button(action: { onSend?(localInput, fileUrl) }) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.system(size: 24))
                        .foregroundColor(
                            localInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                                ? .secondary : .primary)
                }
                .disabled(localInput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                .buttonStyle(.plain)
                .keyboardShortcut(.defaultAction)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .frame(maxWidth: .infinity)
        }
        .onExitCommand {
            onCancel?()
        }
    }

    private func filePreviewView(url: URL) -> some View {
        let isPDF = url.pathExtension.lowercased() == "pdf"

        return ZStack(alignment: .topTrailing) {
            Button(action: { NSWorkspace.shared.open(url) }) {
                if isPDF {
                    // Show PDF icon for PDF files
                    Image(systemName: "doc.text.fill")
                        .font(.system(size: 20))
                        .foregroundColor(.white)
                        .frame(width: 32, height: 32)
                        .background(Color.red.opacity(0.8))
                        .cornerRadius(8)
                } else if let nsImage = NSImage(contentsOf: url) {
                    // Show image preview for image files
                    Image(nsImage: nsImage)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: 32, height: 32)
                        .cornerRadius(8)
                } else {
                    // Fallback for unsupported files
                    Image(systemName: "doc.fill")
                        .font(.system(size: 20))
                        .foregroundColor(.secondary)
                        .frame(width: 32, height: 32)
                        .background(Color.primary.opacity(0.1))
                        .cornerRadius(8)
                }
            }
            .buttonStyle(.plain)

            Button(action: { onRemoveScreenshot?() }) {
                Image(systemName: "xmark")
                    .font(.system(size: 8))
                    .foregroundColor(.primary)
                    .frame(width: 16, height: 16)
                    .background(Color.black.opacity(0.6), in: Circle())
                    .overlay(Circle().strokeBorder(Color.primary.opacity(0.2), lineWidth: 0.5))
            }
            .buttonStyle(.plain)
            .offset(x: 6, y: -6)
        }
    }
}

// MARK: - Shortcut Recording View
private struct ShortcutRecordingView: View {
    @Binding var recordedKeyCode: Int?
    @Binding var recordedModifiers: UInt32?
    @Binding var errorMessage: String?

    let currentShortcut: String
    var onSave: ((Int, UInt32) -> Void)?
    var onCancel: (() -> Void)?

    var body: some View {
        VStack(spacing: 16) {
            Text("Press your desired key combination")
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.primary)

            // Recorder display
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color.secondary.opacity(0.2))
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .strokeBorder(Color.primary, lineWidth: 2)
                    )

                Text(displayText)
                    .font(.system(size: 18, weight: .medium, design: .monospaced))
                    .foregroundColor(.primary)
            }
            .frame(height: 50)
            .padding(.horizontal, 16)

            if let error = errorMessage {
                Text(error)
                    .font(.system(size: 11))
                    .foregroundColor(.red)
                    .padding(.horizontal, 16)
            }

            HStack(spacing: 12) {
                Button("Cancel") {
                    onCancel?()
                }
                .keyboardShortcut(.cancelAction)
                .buttonStyle(.plain)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(Color.secondary.opacity(0.2))
                .cornerRadius(8)

                Button("Save") {
                    if let keyCode = recordedKeyCode, let modifiers = recordedModifiers {
                        onSave?(keyCode, modifiers)
                    }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(recordedKeyCode == nil)
                .buttonStyle(.plain)
                .padding(.horizontal, 16)
                .padding(.vertical, 8)
                .background(recordedKeyCode != nil ? Color.accentColor : Color.secondary.opacity(0.2))
                .foregroundColor(recordedKeyCode != nil ? .white : .secondary)
                .cornerRadius(8)
            }
        }
        .padding(.vertical, 16)
        .frame(height: 160)
    }

    private var displayText: String {
        if let keyCode = recordedKeyCode, let modifiers = recordedModifiers {
            return ShortcutFormatter.format(keyCode: keyCode, modifiers: modifiers)
        }
        return currentShortcut.isEmpty ? "Waiting..." : currentShortcut
    }
}

// MARK: - AI Response View
private struct AIResponseView: View {
    @Binding var isLoading: Bool
    @Binding var responseText: String
    @State private var isQuestionExpanded = false

    let userInput: String
    let fileUrl: URL?

    var onClose: (() -> Void)?
    var onAskFollowUp: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            headerView
                .fixedSize(horizontal: false, vertical: true)
            questionBar
            contentView
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var headerView: some View {
        HStack(spacing: 12) {
            if isLoading {
                LoadingSpinner()
                    .frame(width: 16, height: 16)
                    .background(Color.primary)
                    .clipShape(Circle())
                Text("thinking")
                    .font(.system(size: 14))
                    .foregroundColor(.secondary)
            } else {
                Text("omi says")
                    .font(.system(size: 14))
                    .foregroundColor(.secondary)
            }

            Spacer()

            if !isLoading {
                Button("Ask follow up") {
                    onAskFollowUp?()
                }
                .font(.system(size: 12))
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(Color.primary.opacity(0.1))
                .cornerRadius(8)
                .buttonStyle(.plain)
            }

            Button(action: { onClose?() }) {
                Image(systemName: "xmark")
                    .font(.system(size: 8))
                    .foregroundColor(.secondary)
                    .frame(width: 16, height: 16)
                    .overlay(Circle().strokeBorder(Color.primary.opacity(0.2), lineWidth: 0.5))
            }
            .buttonStyle(.plain)
        }
    }

    private var questionBar: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .top, spacing: 8) {
                if let url = fileUrl {
                    Button(action: { NSWorkspace.shared.open(url) }) {
                        let isPDF = url.pathExtension.lowercased() == "pdf"

                        if isPDF {
                            Image(systemName: "doc.text.fill")
                                .font(.system(size: 12))
                                .foregroundColor(.white)
                                .frame(width: 24, height: 24)
                                .background(Color.red.opacity(0.8))
                                .cornerRadius(4)
                        } else if let nsImage = NSImage(contentsOf: url) {
                            Image(nsImage: nsImage)
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                                .frame(width: 24, height: 24)
                                .cornerRadius(4)
                        } else {
                            Image(systemName: "doc.fill")
                                .font(.system(size: 12))
                                .foregroundColor(.secondary)
                                .frame(width: 24, height: 24)
                                .background(Color.primary.opacity(0.1))
                                .cornerRadius(4)
                        }
                    }
                    .buttonStyle(.plain)
                }

                Group {
                    if isQuestionExpanded {
                        ScrollView {
                            Text(userInput)
                                .font(.system(size: 13))
                                .foregroundColor(.primary)
                                .textSelection(.enabled)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .frame(maxHeight: 120)
                    } else {
                        Text(userInput)
                            .font(.system(size: 13))
                            .foregroundColor(.primary)
                            .lineLimit(1)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }

                if needsExpansion {
                    Button(action: { isQuestionExpanded.toggle() }) {
                        Image(systemName: isQuestionExpanded ? "chevron.up" : "chevron.down")
                            .font(.system(size: 10))
                            .foregroundColor(.secondary)
                            .frame(width: 20, height: 20)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .background(Color.primary.opacity(0.1))
            .cornerRadius(8)
            .contextMenu {
                Button("Copy") {
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(userInput, forType: .string)
                }

                if let url = fileUrl {
                    Divider()

                    Button("Open") {
                        NSWorkspace.shared.open(url)
                    }

                    Button("Show in Finder") {
                        NSWorkspace.shared.activateFileViewerSelecting([url])
                    }
                }
            }
        }
    }

    private var needsExpansion: Bool {
        // Check if text needs more than one line
        let font = NSFont.systemFont(ofSize: 13)
        let attributes = [NSAttributedString.Key.font: font]
        let size = (userInput as NSString).boundingRect(
            with: NSSize(width: 350, height: CGFloat.greatestFiniteMagnitude),
            options: .usesLineFragmentOrigin,
            attributes: attributes
        ).size

        return size.height > font.pointSize * 1.5
    }

    private var contentView: some View {
        Group {
            if isLoading {
                Spacer()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    Markdown(responseText)
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

// MARK: - Main Control Bar View
private struct FloatingControlBarView: View {
    @EnvironmentObject var state: FloatingControlBarState
    weak var window: NSWindow?
    var onPlayPause: () -> Void
    var onAskAI: () -> Void
    var onHide: () -> Void
    var onSendQuery: (String, URL?) -> Void
    var onRemoveScreenshot: () -> Void
    var onSelectFile: () -> Void
    var onCloseAI: () -> Void
    var onAskFollowUp: () -> Void
    var onSaveShortcut: ((Int, UInt32) -> Void)?
    var onCancelShortcutRecording: (() -> Void)?

    var body: some View {
        VStack(spacing: 0) {
            // Show shortcut recording view OR normal control bar
            if state.isRecordingShortcut {
                shortcutRecordingView
            } else {
                // Main control bar - always visible
                controlBarView

                // AI conversation view - conditionally visible
                if state.showingAIConversation {
                    Group {
                        if state.showingAIResponse {
                            aiResponseView
                        } else {
                            aiInputView
                        }
                    }
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .strokeBorder(Color.primary.opacity(0.2), lineWidth: 1)
                    )
                    .padding(.horizontal, 8)
                    .padding(.bottom, 8)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .floatingBackground()
    }

    private var shortcutRecordingView: some View {
        ShortcutRecordingView(
            recordedKeyCode: Binding(
                get: { state.recordedKeyCode },
                set: { state.recordedKeyCode = $0 }
            ),
            recordedModifiers: Binding(
                get: { state.recordedModifiers },
                set: { state.recordedModifiers = $0 }
            ),
            errorMessage: Binding(
                get: { state.shortcutRecordingError },
                set: { state.shortcutRecordingError = $0 }
            ),
            currentShortcut: GlobalShortcutManager.shared.getAskAIShortcutString(),
            onSave: onSaveShortcut,
            onCancel: onCancelShortcutRecording
        )
        .transition(.scale(scale: 0.95).combined(with: .opacity))
    }

    private var controlBarView: some View {
        HStack(spacing: 12) {
            Spacer()

            recordingStatusView

            Spacer().frame(width: 4)

            commandButton(title: "Ask omi", keys: state.currentShortcutKeys, action: onAskAI)

            Spacer().frame(width: 4)

            commandButton(title: "Show/Hide", keys: ["⌘", "\\"], action: onHide)

            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .frame(height: 60)
        .background(DraggableAreaView(targetWindow: window))
    }

    private var aiInputView: some View {
        AskAIInputView(
            userInput: Binding(
                get: { state.aiInputText },
                set: { state.aiInputText = $0 }
            ),
            fileUrl: state.fileUrl,
            onSend: { message, url in
                state.displayedQuery = message
                withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                    state.showingAIResponse = true
                    state.isAILoading = true
                    state.aiResponseText = ""
                }
                onSendQuery(message, url)
            },
            onRemoveScreenshot: onRemoveScreenshot,
            onCaptureScreenshot: {
                onAskAI()
            },
            onSelectFile: onSelectFile,
            onCancel: onCloseAI,
            onHeightChange: { [weak state] height in
                guard let state = state else { return }
                let totalHeight = 60 + height + 24  // control bar + input + padding
                state.inputViewHeight = totalHeight
            }
        )
        .transition(
            .asymmetric(
                insertion: .scale(scale: 0.95).combined(with: .opacity),
                removal: .scale(scale: 0.95).combined(with: .opacity)
            ))
    }

    private var aiResponseView: some View {
        AIResponseView(
            isLoading: Binding(
                get: { state.isAILoading },
                set: { state.isAILoading = $0 }
            ),
            responseText: Binding(
                get: { state.aiResponseText },
                set: { state.aiResponseText = $0 }
            ),
            userInput: state.displayedQuery,
            fileUrl: state.fileUrl,
            onClose: onCloseAI,
            onAskFollowUp: onAskFollowUp
        )
        .transition(
            .asymmetric(
                insertion: .scale(scale: 0.95).combined(with: .opacity),
                removal: .scale(scale: 0.95).combined(with: .opacity)
            ))
    }

    private var recordingStatusView: some View {
        HStack(spacing: 8) {
            Button(action: onPlayPause) {
                if state.isInitialising {
                    LoadingSpinner()
                        .frame(width: 24, height: 24)
                        .frame(width: 28, height: 28)
                        .background(Color.white)
                        .clipShape(Circle())
                } else {
                    Image(systemName: playPauseIcon)
                        .font(.system(size: 12, weight: .bold))
                        .foregroundColor(.black)
                        .frame(width: 28, height: 28)
                        .background(Color.white)
                        .clipShape(Circle())
                        .scaleEffect(state.isRecording && !state.isPaused ? 1.0 : 0.9)
                        .animation(
                            .spring(response: 0.3, dampingFraction: 0.6), value: state.isRecording
                        )
                        .animation(
                            .spring(response: 0.3, dampingFraction: 0.6), value: state.isPaused)
                }
            }
            .buttonStyle(.plain)

            if state.isRecording {
                Text(formattedDuration)
                    .font(.system(size: 14).monospacedDigit())
                    .foregroundColor(.primary)
                    .transition(.scale(scale: 0.8).combined(with: .opacity))
                    .animation(.spring(response: 0.3, dampingFraction: 0.7), value: state.duration)
            }
        }
    }

    private func commandButton(title: String, keys: [String], action: @escaping () -> Void)
        -> some View
    {
        Button(action: action) {
            HStack(spacing: 6) {
                Text(title)
                    .font(.system(size: 14, weight: .medium))
                ForEach(keys, id: \.self) { key in
                    Text(key)
                        .font(.system(size: 11))
                        .foregroundColor(.primary)
                        .frame(width: 20, height: 20)
                        .background(Color.primary.opacity(0.1))
                        .cornerRadius(4)
                }
            }
        }
        .buttonStyle(.plain)
        .help(
            title == "Ask omi"
                ? "Ask omi • \(GlobalShortcutManager.shared.getAskAIShortcutString())" : ""
        )
    }

    private var playPauseIcon: String {
        (state.isRecording && !state.isPaused) ? "pause.fill" : "play.fill"
    }

    private var formattedDuration: String {
        String(format: "%02d:%02d", state.duration / 60, state.duration % 60)
    }
}

// MARK: - AppKit Integration
/// The `NSWindow` subclass that hosts the SwiftUI control bar.
class FloatingControlBar: NSWindow, NSWindowDelegate {
    private static let positionKey = "FloatingControlBarPosition"
    private static let sizeKey = "FloatingControlBarSize"
    private static let defaultSize = NSSize(width: 430, height: 60)
    private static let minSize = NSSize(width: 430, height: 60)
    private static let maxSize = NSSize(width: 1200, height: 1000)

    // Callbacks for button actions
    var onPlayPause: (() -> Void)?
    var onAskAI: ((URL?) -> Void)?
    var onHide: (() -> Void)?
    var onMove: (() -> Void)?
    var onSendQuery: ((String, URL?) -> Void)?

    private var state = FloatingControlBarState()
    private var hostingView: NSHostingView<AnyView>?
    private var isResizingProgrammatically = false
    private var inputHeightCancellable: AnyCancellable?
    private var resizeWorkItem: DispatchWorkItem?

    override init(
        contentRect: NSRect, styleMask style: NSWindow.StyleMask,
        backing backingStoreType: NSWindow.BackingStoreType = .buffered, defer flag: Bool = false
    ) {
        // Always start with fixed control bar size (60pt height)
        // Saved size will only be applied when showing AI response view
        let initialSize = NSSize(width: 430, height: 60)
        let initialRect = NSRect(origin: .zero, size: initialSize)

        super.init(
            contentRect: initialRect,
            styleMask: [.borderless, .utilityWindow],
            backing: backingStoreType,
            defer: flag)

        // Force dark appearance for consistent look regardless of system theme
        self.appearance = NSAppearance(named: .vibrantDark)
        
        self.isOpaque = false
        self.backgroundColor = .clear
        self.hasShadow = false
        self.level = .floating
        self.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        self.isMovableByWindowBackground = false
        self.delegate = self

        // Set size constraints
        self.minSize = FloatingControlBar.minSize
        self.maxSize = FloatingControlBar.maxSize

        setupViews()

        if let savedPosition = UserDefaults.standard.string(forKey: FloatingControlBar.positionKey)
        {
            let origin = NSPointFromString(savedPosition)
            self.setFrameOrigin(origin)
        } else {
            self.center()
        }
    }

    // Allow the window to become the key window to receive keyboard events.
    override var canBecomeKey: Bool {
        return true
    }

    // Allow the window to become the main window.
    override var canBecomeMain: Bool {
        return true
    }

    private func setupViews() {
        // Initialize shortcut keys from current setting
        updateShortcutKeys()

        let swiftUIView = FloatingControlBarView(
            window: self,
            onPlayPause: { [weak self] in self?.onPlayPause?() },
            onAskAI: { [weak self] in self?.handleAskAI() },
            onHide: { [weak self] in self?.hideClicked() },
            onSendQuery: { [weak self] message, url in
                self?.onSendQuery?(message, url)
            },
            onRemoveScreenshot: { [weak self] in
                self?.state.fileUrl = nil
            },
            onSelectFile: { [weak self] in
                self?.selectFile()
            },
            onCloseAI: { [weak self] in
                self?.closeAIConversation()
            },
            onAskFollowUp: { [weak self] in
                self?.resetToInputView()
            },
            onSaveShortcut: { [weak self] keyCode, modifiers in
                self?.saveShortcut(keyCode: keyCode, modifiers: modifiers)
            },
            onCancelShortcutRecording: { [weak self] in
                self?.cancelShortcutRecording()
            }
        ).environmentObject(state)

        hostingView = NSHostingView(rootView: AnyView(
            swiftUIView
                .preferredColorScheme(.dark)
                .environment(\.colorScheme, .dark)
        ))
        hostingView?.appearance = NSAppearance(named: .vibrantDark)
        self.contentView = hostingView

        // Observe drag notifications
        NotificationCenter.default.addObserver(
            forName: .dragDidStart,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.state.isDragging = true
        }

        NotificationCenter.default.addObserver(
            forName: .dragDidEnd,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.state.isDragging = false
        }

        // Observe shortcut changes
        NotificationCenter.default.addObserver(
            forName: GlobalShortcutManager.shortcutDidChangeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.updateShortcutKeys()
        }
    }

    private func updateShortcutKeys() {
        let shortcutString = GlobalShortcutManager.shared.getAskAIShortcutString()
        // Parse the shortcut string into individual key symbols
        state.currentShortcutKeys = parseShortcutString(shortcutString)
    }

    private func parseShortcutString(_ shortcut: String) -> [String] {
        // Split shortcut into modifier symbols and key
        var keys: [String] = []
        let modifiers = ["⌃", "⌥", "⇧", "⌘"]

        for char in shortcut {
            let charString = String(char)
            if modifiers.contains(charString) {
                keys.append(charString)
            } else {
                keys.append(charString)
            }
        }

        return keys.isEmpty ? ["⌘", "↩︎"] : keys
    }

    private func handleAskAI() {
        // Capture screenshot and update state if in input view
        if state.showingAIConversation && !state.showingAIResponse {
            // Already showing input, capture a new screenshot
            let screenshot = ScreenCaptureManager.captureScreen()
            state.fileUrl = screenshot
        } else if state.showingAIConversation {
            // Showing response, close it
            closeAIConversation()
        } else {
            // Not showing conversation, trigger callback to open it
            onAskAI?(state.fileUrl)
        }
    }

    private func closeAIConversation() {
        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
            state.showingAIConversation = false
            state.showingAIResponse = false
            state.aiInputText = ""
            state.aiResponseText = ""
            state.fileUrl = nil
        }

        // Resize to fixed height for control bar only
        resizeToFixedHeight(60, animated: true)
    }

    private func resetToInputView() {
        withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
            state.showingAIResponse = false
            state.aiResponseText = ""
            state.aiInputText = ""
            state.isAILoading = false
            state.fileUrl = nil
            state.inputViewHeight = 120
        }

        resizeToFixedHeight(120, animated: true)
        setupInputHeightObserver()
    }

    private func hideClicked() {
        self.orderOut(nil)
        onHide?()
    }

    private func selectFile() {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowedContentTypes = [.image, .png, .jpeg, .heic, .heif, .gif, .bmp, .tiff, .pdf]
        panel.message = "Select an image or PDF file"

        panel.begin { [weak self] response in
            guard let self = self, response == .OK, let url = panel.url else { return }
            DispatchQueue.main.async {
                self.state.fileUrl = url
            }
        }
    }

    // --- Public Methods for State Update ---
    public func updateRecordingState(
        isRecording: Bool, isPaused: Bool, duration: Int, isInitialising: Bool
    ) {
        DispatchQueue.main.async {
            self.state.isRecording = isRecording
            self.state.isPaused = isPaused
            self.state.duration = duration
            self.state.isInitialising = isInitialising
        }
    }

    public func showAIConversation(fileUrl: URL?) {
        DispatchQueue.main.async {
            withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                self.state.fileUrl = fileUrl
                self.state.showingAIConversation = true
                self.state.showingAIResponse = false
                self.state.isAILoading = true
                self.state.aiInputText = ""
                self.state.aiResponseText = ""
                self.state.inputViewHeight = 100  // Start with minimum height: 60 (control) + 40 (input)
            }

            // Start with minimal height for 1 line input
            self.resizeToFixedHeight(120, animated: true)

            // Observe height changes
            self.setupInputHeightObserver()
        }
    }

    private func setupInputHeightObserver() {
        // Remove any existing observation
        inputHeightCancellable?.cancel()

        // Observe input height changes and resize window accordingly
        inputHeightCancellable = state.$inputViewHeight
            .removeDuplicates()
            .debounce(for: .milliseconds(50), scheduler: DispatchQueue.main)
            .sink { [weak self] height in
                guard let self = self,
                    self.state.showingAIConversation,
                    !self.state.showingAIResponse
                else { return }
                self.resizeToFixedHeight(height)
            }
    }

    public func updateAIResponse(type: String, text: String) {
        DispatchQueue.main.async {
            // Only process AI responses if the AI conversation is still visible
            guard self.state.showingAIConversation else {
                return
            }
            
            switch type {
            case "data":
                if self.state.isAILoading {
                    withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                        self.state.isAILoading = false
                        // First data arrived, show response view and resize to saved/default height
                        self.state.showingAIResponse = true
                    }
                    self.resizeToResponseHeight(animated: true)
                }
                self.state.aiResponseText += text
            case "done":
                withAnimation(.easeOut(duration: 0.2)) {
                    self.state.isAILoading = false
                }
                if !text.isEmpty {
                    self.state.aiResponseText = text
                }
            case "error":
                withAnimation(.easeOut(duration: 0.2)) {
                    self.state.isAILoading = false
                }
                self.state.aiResponseText = text.isEmpty ? "An unknown error occurred." : text
            default:
                break
            }
        }
    }

    // MARK: - Window Geometry Helpers

    /// Calculates the origin point to maintain top-left corner when resizing
    private func originForTopLeftAnchor(newSize: NSSize) -> NSPoint {
        NSPoint(
            x: frame.origin.x,
            y: frame.origin.y + (frame.height - newSize.height)
        )
    }

    /// Resizes window while anchoring from top-left corner
    private func resizeAnchored(to size: NSSize, makeResizable: Bool, animated: Bool = false) {
        // Enforce minimum width constraint
        let constrainedSize = NSSize(
            width: max(size.width, FloatingControlBar.minSize.width),
            height: max(size.height, FloatingControlBar.minSize.height)
        )

        let newOrigin = originForTopLeftAnchor(newSize: constrainedSize)

        if makeResizable {
            styleMask.insert(.resizable)
        } else {
            styleMask.remove(.resizable)
        }

        isResizingProgrammatically = true

        // Smooth resize animation
        NSAnimationContext.beginGrouping()
        NSAnimationContext.current.duration = animated ? 0.3 : 0
        NSAnimationContext.current.timingFunction = CAMediaTimingFunction(name: .easeInEaseOut)
        self.setFrame(
            NSRect(origin: newOrigin, size: constrainedSize), display: true, animate: animated)
        NSAnimationContext.endGrouping()

        self.isResizingProgrammatically = false
    }

    /// Resizes to a fixed height with fixed width (for control bar and input views)
    private func resizeToFixedHeight(_ height: CGFloat, animated: Bool = false) {
        // Cancel pending resize
        resizeWorkItem?.cancel()

        let size = NSSize(width: 430, height: height)

        // Batch resize requests
        resizeWorkItem = DispatchWorkItem { [weak self] in
            self?.resizeAnchored(to: size, makeResizable: false, animated: animated)
        }

        if let workItem = resizeWorkItem {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05, execute: workItem)
        }
    }

    /// Resizes to saved or default size (for AI response view)
    private func resizeToResponseHeight(animated: Bool = false) {
        let savedSize = UserDefaults.standard.string(forKey: FloatingControlBar.sizeKey)
            .map(NSSizeFromString)

        let targetSize =
            savedSize.map {
                NSSize(
                    width: max($0.width, FloatingControlBar.minSize.width),
                    height: max($0.height, 430)
                )
            } ?? FloatingControlBar.defaultSize

        resizeAnchored(to: targetSize, makeResizable: true, animated: animated)
    }

    private func saveShortcut(keyCode: Int, modifiers: UInt32) {
        GlobalShortcutManager.shared.setAskAIShortcut(keyCode: keyCode, modifiers: modifiers)
        cancelShortcutRecording()
    }

    private func cancelShortcutRecording() {
        DispatchQueue.main.async {
            withAnimation(.spring(response: 0.4, dampingFraction: 0.8)) {
                self.state.isRecordingShortcut = false
                self.state.recordedKeyCode = nil
                self.state.recordedModifiers = nil
                self.state.shortcutRecordingError = nil
            }

            // Resize back to control bar height
            self.resizeToFixedHeight(60, animated: true)
        }
    }

    override func keyDown(with event: NSEvent) {
        // Only handle key events when in shortcut recording mode
        guard state.isRecordingShortcut else {
            super.keyDown(with: event)
            return
        }

        let keyCode = Int(event.keyCode)
        let modifiers = event.modifierFlags.carbonModifiers

        // Ignore modifier-only presses
        guard !event.modifierFlags.intersection([.command, .control, .option, .shift]).isEmpty
        else {
            return
        }

        // Validate the shortcut
        if !ShortcutValidator.isValid(keyCode: keyCode, modifiers: modifiers) {
            state.shortcutRecordingError =
                "This key combination is reserved or invalid. Please try another."
            state.recordedKeyCode = nil
            state.recordedModifiers = nil
            return
        }

        // Valid shortcut recorded
        state.recordedKeyCode = keyCode
        state.recordedModifiers = modifiers
        state.shortcutRecordingError = nil
    }

    public func resetPosition() {
        UserDefaults.standard.removeObject(forKey: FloatingControlBar.positionKey)
        self.center()
    }

    @objc func windowDidMove(_ notification: Notification) {
        UserDefaults.standard.set(
            NSStringFromPoint(self.frame.origin), forKey: FloatingControlBar.positionKey)
        onMove?()
    }

    func windowWillResize(_ sender: NSWindow, to frameSize: NSSize) -> NSSize {
        // Enforce minimum constraints during resize
        return NSSize(
            width: max(frameSize.width, FloatingControlBar.minSize.width),
            height: max(frameSize.height, FloatingControlBar.minSize.height)
        )
    }

    func windowDidResize(_ notification: Notification) {
        // Only save size when user manually resizes AND AI response is visible
        // (Don't save during programmatic resizes or when showing fixed-height views)
        if !isResizingProgrammatically && state.showingAIResponse {
            UserDefaults.standard.set(
                NSStringFromSize(self.frame.size), forKey: FloatingControlBar.sizeKey)
        }
    }
}
