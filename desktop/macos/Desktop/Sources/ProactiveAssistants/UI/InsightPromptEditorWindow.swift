import Cocoa
import OmiTheme
import SwiftUI

/// NSWindow subclass that hosts the Advice Prompt Editor SwiftUI view
class InsightPromptEditorWindow: NSWindow {
  private static var sharedWindow: InsightPromptEditorWindow?

  /// Shows the insight prompt editor window, creating it if necessary
  static func show() {
    if let existingWindow = sharedWindow {
      existingWindow.makeKeyAndOrderFront(nil)
      NSApp.activate()
      return
    }

    let window = InsightPromptEditorWindow()
    sharedWindow = window
    window.makeKeyAndOrderFront(nil)
    NSApp.activate()
  }

  /// Closes the insight prompt editor window
  static func close() {
    sharedWindow?.close()
    sharedWindow = nil
  }

  private init() {
    let contentRect = NSRect(x: 0, y: 0, width: 600, height: 500)

    super.init(
      contentRect: contentRect,
      styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
      backing: .buffered,
      defer: false
    )

    self.title = "Edit Insight Prompt"
    self.isReleasedWhenClosed = false
    // The inside of a titled window is glass: transparent, light-pinned, and shadowed by its own
    // frame (`WindowGlass.Kind.titled`). Without the pin the title bar and the traffic lights stay in
    // the machine's appearance — a dark title bar on a white sheet on a Dark Mac.
    WindowGlass.wear(self, as: .titled)
    self.delegate = self
    self.minSize = NSSize(width: 500, height: 400)

    // Center on screen
    self.center()

    // Create SwiftUI view
    let editorView = AssistantPromptEditorView(
      store: .insight,
      onClose: { [weak self] in
        self?.close()
      })

    let hostingView = NSHostingView(rootView: editorView.withFontScaling())
    self.contentView = hostingView
  }
}

// MARK: - NSWindowDelegate

extension InsightPromptEditorWindow: NSWindowDelegate {
  func windowWillClose(_ notification: Notification) {
    InsightPromptEditorWindow.sharedWindow = nil
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    AssistantPromptEditorView(store: .insight)
  }
#endif
