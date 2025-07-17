import Cocoa

// Custom NSWindow that can become key window to accept input
class KeyableWindow: NSWindow {
    override var canBecomeKey: Bool {
        return true
    }
    
    override var canBecomeMain: Bool {
        return false  // Don't become main to avoid stealing focus from other apps
    }
    
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool {
        return true
    }
}
