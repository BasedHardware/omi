import AppKit
import ContextCore
import SwiftUI

/// The settings window, owned by AppKit rather than by SwiftUI.
///
/// Follows `RewindWindow` exactly, for the same reasons: the app is `LSUIElement` with no
/// `WindowGroup`, so there is no SwiftUI scene graph to add a window to. `isReleasedWhenClosed = false`
/// keeps the instance — and with it the measured storage figure and the loaded application inventory —
/// alive for the next open, and the screen is chosen from the pointer rather than `NSScreen.main`, which
/// on a menu-bar-only app is routinely the display the user is not looking at.
///
/// The `NSHostingView` goes **inside a plain container** `NSView` rather than being the `contentView`.
/// Making it the content view makes it try to negotiate window sizing, which re-enters constraint
/// updates and crashes on macOS 26. `RewindWindow` carries the same note.
@MainActor
enum SettingsWindow {

    private static var current: NSWindow?
    private static var exclusions: ExclusionsObserver?
    /// Held so a second `present(pane:)` can move an already-open window to another pane. The sidebar
    /// writes to the same object, so there is one answer to "which pane is showing".
    private static var selection: SettingsSelection?
    /// The global-shortcut layer is being built separately; until it lands the window binds to the
    /// in-memory stand-in, which keeps real state and registers nothing. Assigning to this before the
    /// first `present()` is how the real provider is swapped in.
    static var shortcutProvider: ShortcutBindingProvider = InMemoryShortcutBindings()

    /// - Parameter pane: which pane to open on. A caller that has a reason to be specific — the
    ///   permissions row in the menu bar wanting Capture, a privacy prompt wanting Exclusions — should
    ///   say so rather than dropping the user on General to find it.
    static func present(pane: SettingsPane = .general) {
        if let window = current {
            // A re-open should reflect anything that changed outside the app — a login item removed in
            // System Settings, an exclusions file edited by hand.
            exclusions?.refresh()
            selection?.pane = pane
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            return
        }

        let pointer = NSEvent.mouseLocation
        guard
            let screen = NSScreen.screens.first(where: { NSMouseInRect(pointer, $0.frame, false) })
                ?? NSScreen.main
        else {
            ContextLog.error("no screen available to present settings", "settings")
            return
        }

        let observer = ExclusionsObserver()
        exclusions = observer
        let selected = SettingsSelection(pane: pane)
        selection = selected

        let window = NSWindow(
            contentRect: centredFrame(on: screen),
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false)
        window.title = "Settings"
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true
        window.minSize = SettingsMetrics.minimumSize
        window.isReleasedWhenClosed = false
        // Deliberately `.normal`: settings is worked in beside other windows, not floated over them.
        window.level = .normal

        let container = NSView(frame: NSRect(origin: .zero, size: window.frame.size))
        container.autoresizingMask = [.width, .height]
        window.contentView = container

        let hosting = NSHostingView(
            rootView: SettingsView(
                store: SettingsStore.shared,
                exclusions: observer,
                shortcuts: shortcutProvider,
                selection: selected))
        // No `.intrinsicContentSize`, so the pane can fill a resized window; `.minSize`/`.maxSize` keep
        // the real constraints. See `RewindWindow` for what the other spellings break.
        hosting.sizingOptions = [.minSize, .maxSize]
        hosting.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(hosting)
        NSLayoutConstraint.activate([
            hosting.leadingAnchor.constraint(equalTo: container.leadingAnchor),
            hosting.trailingAnchor.constraint(equalTo: container.trailingAnchor),
            hosting.topAnchor.constraint(equalTo: container.topAnchor),
            hosting.bottomAnchor.constraint(equalTo: container.bottomAnchor),
        ])

        current = window
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    static func dismiss() {
        current?.orderOut(nil)
    }

    static var isVisible: Bool { current?.isVisible ?? false }

    private static func centredFrame(on screen: NSScreen) -> NSRect {
        let visible = screen.visibleFrame
        let size = NSSize(
            width: min(SettingsMetrics.windowSize.width, visible.width - 40),
            height: min(SettingsMetrics.windowSize.height, visible.height - 40))
        return NSRect(
            x: (visible.midX - size.width / 2).rounded(),
            y: (visible.midY - size.height / 2).rounded(),
            width: size.width,
            height: size.height)
    }
}
