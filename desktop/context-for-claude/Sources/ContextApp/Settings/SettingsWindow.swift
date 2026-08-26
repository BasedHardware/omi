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
    /// The real provider is `LiveShortcutBindings`, assigned in `ContextApp` beside
    /// `GlobalShortcuts.shared.start()` so the ordering is visible at the call site.
    ///
    /// The default is deliberately still the in-memory stand-in, which keeps state and registers
    /// nothing: this is a `static var` read by `present()`, and a default that reached into
    /// `GlobalShortcuts` would arm Carbon hot keys from a SwiftUI preview or from a test that only
    /// wanted to open the window. The cost is that dropping the assignment silently returns the pane
    /// to reporting success into a dictionary — which is the bug that shipped — so
    /// `ShortcutBindingsTests` pins the live provider's behaviour rather than the stand-in's.
    static var shortcutProvider: ShortcutBindingProvider = InMemoryShortcutBindings()

    /// - Parameter via: the route that asked for it — the panel's gear, the menu bar's row, or ⌘,.
    ///   Reported here rather than at those three, so a fourth cannot arrive uncounted.
    /// - Parameter pane: which pane to open on. A caller that has a reason to be specific — the
    ///   permissions row in the menu bar wanting Capture, a privacy prompt wanting Exclusions — should
    ///   say so rather than dropping the user on General to find it.
    static func present(via: AnalyticsEvent.OpenSource, pane: SettingsPane = .general) {
        if let window = current {
            // A re-open should reflect anything that changed outside the app — a login item removed in
            // System Settings, an exclusions file edited by hand.
            exclusions?.refresh()
            selection?.pane = pane
            window.makeKeyAndOrderFront(nil)
            NSApp.activate(ignoringOtherApps: true)
            // A window brought forward is a visit to Settings; which branch it took is a fact about
            // this process's history rather than about the user. Reported after the window is up, so
            // the screen guard below — which declines rather than presenting — reports nothing.
            ContextAnalytics.record(.surfaceOpened(.settings, via: via))
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
        window.isMovableByWindowBackground = true
        window.minSize = SettingsMetrics.minimumSize
        window.isReleasedWhenClosed = false
        // Deliberately `.normal`: settings is worked in beside other windows, not floated over them.
        window.level = .normal
        // The window-side half of the glass — transparent ground, the light pin, and a title bar the
        // panel runs edge to edge underneath. One call rather than the five properties this file used
        // to restate: `WindowGlass` is where "a glass window paints no ground of its own" is stated
        // once and asserted once, so this window cannot drift from the timeline or the search bar.
        WindowGlass.wear(window, as: .titled)

        // The shared glass, full-bleed: no corner and no shadow of its own, because the window frame
        // already owns both. `RewindWindow` carries the same pair of views and the same reason.
        let container = InkGlassView(
            frame: NSRect(origin: .zero, size: window.frame.size), style: .fullBleed)
        container.autoresizingMask = [.width, .height]
        window.contentView = container
        container.layoutSubtreeIfNeeded()

        let hosting = NSHostingView(
            rootView: SettingsView(
                store: SettingsStore.shared,
                exclusions: observer,
                shortcuts: shortcutProvider,
                selection: selected))
        // No `.intrinsicContentSize`, so the pane can fill a resized window; `.minSize`/`.maxSize` keep
        // the real constraints. See `RewindWindow` for what the other spellings break.
        //
        // Constrained to the glass *host* rather than handed to `InkGlassView.setContent`, which is
        // the seam a floating panel uses: `setContent` is frame-and-autoresizing, and this window is
        // resizable with a minimum size that only Auto Layout expresses. It is the same rectangle
        // either way — `.fullBleed` is inset 0, so the panel fills its host exactly — and the ground
        // stays entirely AppKit's, which is the property that matters. `SettingsView` therefore paints
        // no background of its own; see the note on its `body`.
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
        ContextAnalytics.record(.surfaceOpened(.settings, via: via))
    }

    static func dismiss() {
        current?.orderOut(nil)
    }

    static var isVisible: Bool { current?.isVisible ?? false }

    /// The Settings window itself, for the one thing that has to know which window an event was
    /// delivered to: the shortcut recorder's key monitor. See `ShortcutRecorderScope`.
    static var window: NSWindow? { current }

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
