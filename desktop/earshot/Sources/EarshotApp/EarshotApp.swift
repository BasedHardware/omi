import AppKit
import CoreText
import SwiftUI

/// Earshot's entire scene graph: one menu bar item, one popover.
///
/// There is deliberately no `WindowGroup`. `LSUIElement` in Info.plist keeps the app out of the
/// Dock and the ⌘-Tab switcher, and onboarding is an AppKit window owned by `OnboardingWindow`
/// rather than a SwiftUI scene — so a scene here would only ever be an empty window the user could
/// summon by accident.
@main
struct EarshotApp: App {
    @NSApplicationDelegateAdaptor(EarshotAppDelegate.self) private var delegate

    // `@StateObject` takes an autoclosure, so the main-actor-isolated singleton is not touched until
    // SwiftUI first evaluates `body` on the main actor.
    @StateObject private var engine = Engine.shared

    var body: some Scene {
        MenuBarExtra {
            StatusView()
        } label: {
            // The Earshot mark, drawn as a template image. Not the eight-dot omi mark: at 18 pt a
            // ring of dots is indistinguishable from a loading spinner, so it stays in onboarding
            // where it has room to read as a mark.
            //
            // The menu bar answers "is it listening?" without a click — the mark is struck through
            // when it is not.
            Image(nsImage: engine.isCapturing ? EarshotMark.menuBar : EarshotMark.menuBarPaused)
        }
        .menuBarExtraStyle(.window)
    }
}

/// Everything that must happen once per process, in the order the rest of the app assumes:
/// activation policy before any window can steal focus, fonts before anything draws, capture before
/// the user can look at its status, onboarding last.
final class EarshotAppDelegate: NSObject, NSApplicationDelegate {
    /// Set by the onboarding flow once the user has finished it.
    private static let onboardedKey = "earshot.onboarded"

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Belt and braces. `LSUIElement` in the generated Info.plist should already have done this;
        // if that plist is ever wrong the app would otherwise appear in the Dock and pull focus on
        // every launch — the single most visible way this product could stop being ambient.
        NSApp.setActivationPolicy(.accessory)

        registerBundledFonts()

        MainActor.assumeIsolated {
            Engine.shared.start()

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
        MainActor.assumeIsolated { Engine.shared.pause() }
    }

    /// The typefaces ship as loose `.ttf` files in `Contents/Resources/Fonts` (assembled by
    /// `scripts/build.sh`), not in a SwiftPM resource bundle — an executable target has no
    /// `Bundle.module` to reach for, and the generated accessor bakes in a build-machine path that
    /// does not survive installation.
    private func registerBundledFonts() {
        guard let directory = Bundle.main.resourceURL?.appendingPathComponent("Fonts", isDirectory: true),
            let contents = try? FileManager.default.contentsOfDirectory(
                at: directory, includingPropertiesForKeys: nil)
        else {
            EarshotLog.error("no bundled Fonts directory; Inter and Literata fall back to the system font", "shell")
            return
        }

        var registered = 0
        for url in contents where url.pathExtension.lowercased() == "ttf" {
            var error: Unmanaged<CFError>?
            if CTFontManagerRegisterFontsForURL(url as CFURL, .process, &error) {
                registered += 1
                continue
            }
            // Never fatal: a face that will not register costs us a typeface, not a launch.
            let reason = error?.takeRetainedValue().localizedDescription ?? "unknown error"
            EarshotLog.error("font \(url.lastPathComponent) not registered (\(reason))", "shell")
        }
        EarshotLog.info("registered \(registered) bundled fonts", "shell")
    }
}
