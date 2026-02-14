import Cocoa
import SwiftUI

/// Window for editing the memory extraction prompt
class MemoryPromptEditorWindow: NSWindow {
    private static var sharedWindow: MemoryPromptEditorWindow?

    static func show() {
        if let existing = sharedWindow, existing.isVisible {
            existing.makeKeyAndOrderFront(nil)
            return
        }

        let window = MemoryPromptEditorWindow()
        sharedWindow = window
        window.makeKeyAndOrderFront(nil)
        window.center()
    }

    init() {
        super.init(
            contentRect: NSRect(x: 0, y: 0, width: 700, height: 600),
            styleMask: [.titled, .closable, .resizable, .miniaturizable],
            backing: .buffered,
            defer: false
        )

        title = "Memory Extraction Prompt"
        minSize = NSSize(width: 500, height: 400)
        isReleasedWhenClosed = false

        contentView = NSHostingView(rootView: MemoryPromptEditorView(onClose: { [weak self] in
            self?.close()
        }).withFontScaling())
    }
}

struct MemoryPromptEditorView: View {
    @State private var promptText: String
    @State private var hasChanges: Bool = false
    @State private var showingResetAlert: Bool = false

    var onClose: (() -> Void)?

    init(onClose: (() -> Void)? = nil) {
        self.onClose = onClose
        _promptText = State(initialValue: MemoryAssistantSettings.shared.analysisPrompt)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Header
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Memory Extraction Prompt")
                        .scaledFont(size: 16, weight: .semibold)

                    Text("Customize how the AI extracts memories from screenshots")
                        .scaledFont(size: 12)
                        .foregroundColor(.secondary)
                }

                Spacer()

                if hasChanges {
                    Text("Unsaved changes")
                        .scaledFont(size: 11)
                        .foregroundColor(.orange)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.orange.opacity(0.1))
                        .cornerRadius(4)
                }
            }
            .padding()

            Divider()

            // Editor
            TextEditor(text: $promptText)
                .scaledFont(size: 13, design: .monospaced)
                .padding(8)
                .onChange(of: promptText) { _, newValue in
                    hasChanges = newValue != MemoryAssistantSettings.shared.analysisPrompt
                }

            Divider()

            // Footer with buttons
            HStack {
                Button("Reset to Default") {
                    showingResetAlert = true
                }
                .alert("Reset Prompt?", isPresented: $showingResetAlert) {
                    Button("Cancel", role: .cancel) {}
                    Button("Reset", role: .destructive) {
                        promptText = MemoryAssistantSettings.defaultAnalysisPrompt
                        MemoryAssistantSettings.shared.resetPromptToDefault()
                        hasChanges = false
                    }
                } message: {
                    Text("This will reset the memory extraction prompt to its default value. This cannot be undone.")
                }

                Spacer()

                Button("Cancel") {
                    onClose?()
                }
                .keyboardShortcut(.escape, modifiers: [])

                Button("Save") {
                    MemoryAssistantSettings.shared.analysisPrompt = promptText
                    hasChanges = false
                    onClose?()
                }
                .keyboardShortcut(.return, modifiers: .command)
                .buttonStyle(.borderedProminent)
                .disabled(!hasChanges)
            }
            .padding()
        }
        .frame(minWidth: 500, minHeight: 400)
    }
}

#Preview {
    MemoryPromptEditorView()
        .frame(width: 700, height: 600)
}
