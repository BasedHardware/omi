import Cocoa
import SwiftUI
import OmiTheme

/// SwiftUI view for editing the task extraction prompt
struct TaskPromptEditorView: View {
    @State private var prompt: String
    @Environment(\.dismiss) private var dismiss

    var onClose: (() -> Void)?

    init(onClose: (() -> Void)? = nil) {
        self.onClose = onClose
        _prompt = State(initialValue: TaskAssistantSettings.shared.analysisPrompt)
    }

    var body: some View {
        VStack(spacing: OmiSpacing.lg) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: OmiSpacing.xxs) {
                    Text("Task Extraction Prompt")
                        .scaledFont(size: OmiType.subheading, weight: .semibold)
                        .foregroundColor(.primary)

                    Text("Customize the AI instructions for task extraction")
                        .scaledFont(size: OmiType.caption)
                        .foregroundColor(.secondary)
                }

                Spacer()

                // Reset button
                Button(action: resetToDefault) {
                    HStack(spacing: OmiSpacing.xxs) {
                        Image(systemName: "arrow.counterclockwise")
                            .scaledFont(size: OmiType.caption)
                        Text("Reset to Default")
                            .scaledFont(size: OmiType.caption)
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }

            // Text editor
            TextEditor(text: $prompt)
                .scaledFont(size: OmiType.body, design: .monospaced)
                .padding(OmiSpacing.md)
                .background(
                    RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                        .fill(Color(nsColor: .textBackgroundColor))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: OmiChrome.elementRadius)
                        .strokeBorder(Color.primary.opacity(0.2), lineWidth: 1)
                )
                .onChange(of: prompt) { _, newValue in
                    TaskAssistantSettings.shared.analysisPrompt = newValue
                }

            // Footer with character count
            HStack {
                Text("\(prompt.count) characters")
                    .scaledFont(size: OmiType.caption)
                    .foregroundColor(.secondary)

                Spacer()

                Button("Done") {
                    onClose?()
                }
                .keyboardShortcut(.return, modifiers: .command)
                .buttonStyle(.borderedProminent)
                .controlSize(.regular)
            }
        }
        .padding(OmiSpacing.xl)
        .frame(width: 600, height: 500)
        .background(Color(nsColor: .windowBackgroundColor))
    }

    private func resetToDefault() {
        TaskAssistantSettings.shared.resetPromptToDefault()
        prompt = TaskAssistantSettings.shared.analysisPrompt
    }
}

/// NSWindow subclass that hosts the Task Prompt Editor SwiftUI view
class TaskPromptEditorWindow: NSWindow {
    private static var sharedWindow: TaskPromptEditorWindow?

    /// Shows the task prompt editor window, creating it if necessary
    static func show() {
        if let existingWindow = sharedWindow {
            existingWindow.makeKeyAndOrderFront(nil)
            NSApp.activate()
            return
        }

        let window = TaskPromptEditorWindow()
        sharedWindow = window
        window.makeKeyAndOrderFront(nil)
        NSApp.activate()
    }

    /// Closes the task prompt editor window
    static func close() {
        sharedWindow?.close()
        sharedWindow = nil
    }

    private init() {
        let contentRect = NSRect(x: 0, y: 0, width: 600, height: 500)

        super.init(
            contentRect: contentRect,
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )

        self.title = "Edit Task Extraction Prompt"
        self.isReleasedWhenClosed = false
        self.delegate = self
        self.minSize = NSSize(width: 500, height: 400)

        // Center on screen
        self.center()

        // Create SwiftUI view
        let editorView = TaskPromptEditorView(onClose: { [weak self] in
            self?.close()
        })

        let hostingView = NSHostingView(rootView: editorView.withFontScaling())
        self.contentView = hostingView
    }
}

// MARK: - NSWindowDelegate

extension TaskPromptEditorWindow: NSWindowDelegate {
    func windowWillClose(_ notification: Notification) {
        TaskPromptEditorWindow.sharedWindow = nil
    }
}

#if canImport(PreviewsMacros)
#Preview {
    TaskPromptEditorView()
}
#endif
