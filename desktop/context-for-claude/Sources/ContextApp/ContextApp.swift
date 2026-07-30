import AppKit
import CoreText
import SwiftUI

/// Context for Claude's entire scene graph: one menu bar item, one popover.
///
/// There is deliberately no `WindowGroup`. `LSUIElement` in Info.plist keeps the app out of the
/// Dock and the ⌘-Tab switcher, and onboarding is an AppKit window owned by `OnboardingWindow`
/// rather than a SwiftUI scene — so a scene here would only ever be an empty window the user could
/// summon by accident.
@main
struct ContextApp: App {
    @NSApplicationDelegateAdaptor(ContextAppDelegate.self) private var delegate

    // `@StateObject` takes an autoclosure, so the main-actor-isolated singleton is not touched until
    // SwiftUI first evaluates `body` on the main actor.
    @StateObject private var engine = Engine.shared

    var body: some Scene {
        // The status item is an `NSStatusItem` created by the delegate, not a `MenuBarExtra`.
        // `MenuBarExtra` exposes no way to find out where its own button ended up on screen, and
        // the button is not in the window list either — so "I live up here" had nothing to point
        // at. `NSStatusItem.button.window` gives the exact frame, which is what the onboarding
        // spotlight needs to ring the icon and walk the cursor to it.
        //
        // A SwiftUI `App` still needs one scene. `Settings` is the only one that never shows itself
        // unaided, which is what an app with no windows wants.
        Settings { EmptyView() }
    }
}

/// Everything that must happen once per process, in the order the rest of the app assumes:
/// activation policy before any window can steal focus, fonts before anything draws, capture before
/// the user can look at its status, onboarding last.
final class ContextAppDelegate: NSObject, NSApplicationDelegate {
    /// Set by the onboarding flow once the user has finished it.
    private static let onboardedKey = "context.onboarded"

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Belt and braces. `LSUIElement` in the generated Info.plist should already have done this;
        // if that plist is ever wrong the app would otherwise appear in the Dock and pull focus on
        // every launch — the single most visible way this product could stop being ambient.
        NSApp.setActivationPolicy(.accessory)

        // Deliberately no `NSApp.appearance` override. Pinning the process to `.aqua` rendered a
        // light popover inside a dark system menu — the single loudest reason the colours read as
        // wrong — and it also overrode the appearance of every AppKit surface the app does not draw
        // itself: focus rings, scrollers, the popover's own window background and corner rounding.
        // Every colour the app draws now comes from a system semantic colour (`Ink`), so following
        // the system is both correct and the smaller amount of code.

        registerBundledFonts()

        // The bundled faces are only reachable after registration; anything that resolved a role
        // before this point cached a system-font stand-in. Nothing draws this early today, and this
        // keeps that true if something ever does.
        InkFonts.invalidate()

        MainActor.assumeIsolated {
            // Before Engine.start(), so the icon exists the moment there is state to show — and
            // before onboarding, which finishes by pointing at it.
            StatusItemController.shared.install()
            Engine.shared.start()

            // Decode the four onboarding cues now so the first one does not pay for it mid-beat.
            // Safe with the assets missing: the layer degrades to silence rather than throwing,
            // because nothing about onboarding may depend on audio succeeding.
            Sound.prepare()

            // Double-tap Command opens the timeline, double-tap Command-Shift opens search. Both are
            // rebindable, and both simply do not fire while Accessibility is ungranted — a global
            // monitor cannot see keys without it, and pretending to be armed would be worse.
            GlobalShortcuts.shared.start { action in
                switch action {
                case .openSearch:
                    SearchBarWindow.toggle()
                case .openTimeline:
                    // The store opens lazily on the engine's own queue, so ask at trigger time
                    // rather than at launch. Nil means it is not open yet: decline to put a timeline
                    // over nothing instead of showing an empty one.
                    guard let store = Engine.shared.contextStore else { return }
                    RewindWindow.present(
                        store: store,
                        onOpenSettings: { SettingsWindow.present() },
                        onSearch: { query in SearchBarWindow.present(prefill: query) })
                }
            }

            if !UserDefaults.standard.bool(forKey: Self.onboardedKey) {
                OnboardingWindow.present()
            }
        }
    }

    /// Menu-bar-only: dismissing onboarding must never take the process with it.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    func applicationWillTerminate(_ notification: Notification) {
        // Closes the open session and writes a final heartbeat. Without this the last session stays
        // open forever and `status()` reports a recording that stopped hours ago.
        MainActor.assumeIsolated {
            // The tutorial owns borderless overlay windows and the menu-bar spotlight. Quitting
            // mid-walkthrough without tearing them down leaves them on screen with no process behind
            // them, which the user cannot dismiss.
            Tutorial.abandon()
            Engine.shared.pause()
        }
    }

    /// The typefaces ship as loose font files in `Contents/Resources/Fonts` (assembled by
    /// `scripts/build.sh`), not in a SwiftPM resource bundle — an executable target has no
    /// `Bundle.module` to reach for, and the generated accessor bakes in a build-machine path that
    /// does not survive installation.
    ///
    /// Both `.otf` and `.ttf`: Open Runde ships as OpenType/CFF, and an extension filter that knew
    /// only about the previous family's `.ttf` would silently drop every face in the product.
    private static let fontExtensions: Set<String> = ["otf", "ttf"]

    private func registerBundledFonts() {
        guard let directory = Bundle.main.resourceURL?.appendingPathComponent("Fonts", isDirectory: true),
            let contents = try? FileManager.default.contentsOfDirectory(
                at: directory, includingPropertiesForKeys: nil)
        else {
            ContextLog.error("no bundled Fonts directory; Open Runde falls back to the system font", "shell")
            return
        }

        var registered = 0
        for url in contents where Self.fontExtensions.contains(url.pathExtension.lowercased()) {
            var error: Unmanaged<CFError>?
            if CTFontManagerRegisterFontsForURL(url as CFURL, .process, &error) {
                registered += 1
                continue
            }
            // Never fatal: a face that will not register costs us a typeface, not a launch.
            let reason = error?.takeRetainedValue().localizedDescription ?? "unknown error"
            ContextLog.error("font \(url.lastPathComponent) not registered (\(reason))", "shell")
        }
        ContextLog.info("registered \(registered) bundled fonts", "shell")
    }
}
