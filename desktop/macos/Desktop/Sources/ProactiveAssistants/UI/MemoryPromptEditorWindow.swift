import Cocoa
import OmiTheme
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
      styleMask: [.titled, .closable, .resizable, .miniaturizable, .fullSizeContentView],
      backing: .buffered,
      defer: false
    )

    title = "Memory Extraction Prompt"
    minSize = NSSize(width: 500, height: 400)
    isReleasedWhenClosed = false
    // The inside of a titled window is glass: transparent, light-pinned, and shadowed by its own
    // frame (`WindowGlass.Kind.titled`). Without the pin the title bar and the traffic lights stay in
    // the machine's appearance — a dark title bar on a white sheet on a Dark Mac.
    WindowGlass.wear(self, as: .titled)

    contentView = NSHostingView(
      rootView: AssistantPromptEditorView(
        store: .memory,
        onClose: { [weak self] in
          self?.close()
        }
      ).withFontScaling())
  }
}

#if canImport(PreviewsMacros)
  #Preview {
    AssistantPromptEditorView(store: .memory)
      .frame(width: 700, height: 600)
  }
#endif
