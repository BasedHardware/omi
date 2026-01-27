import Cocoa
import SwiftUI

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
        VStack(spacing: 16) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Task Extraction Prompt")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(.primary)

                    Text("Customize the AI instructions for task extraction")
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                }

                Spacer()

                // Reset button
                Button(action: resetToDefault) {
                    HStack(spacing: 4) {
                        Image(systemName: "arrow.counterclockwise")
                            .font(.system(size: 11))
                        Text("Reset to Default")
                            .font(.system(size: 12))
                    }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }

            // Text editor
            TextEditor(text: $prompt)
                .font(.system(size: 13, design: .monospaced))
                .padding(12)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color(nsColor: .textBackgroundColor))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .strokeBorder(Color.primary.opacity(0.2), lineWidth: 1)
                )
                .onChange(of: prompt) { newValue in
                    TaskAssistantSettings.shared.analysisPrompt = newValue
                }

            // Footer with character count
            HStack {
                Text("\(prompt.count) characters")
                    .font(.system(size: 11))
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
        .padding(20)
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
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        let window = TaskPromptEditorWindow()
        sharedWindow = window
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
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

        let hostingView = NSHostingView(rootView: editorView)
        self.contentView = hostingView
    }
}

// MARK: - NSWindowDelegate

extension TaskPromptEditorWindow: NSWindowDelegate {
    func windowWillClose(_ notification: Notification) {
        TaskPromptEditorWindow.sharedWindow = nil
    }
}

#Preview {
    TaskPromptEditorView()
}
