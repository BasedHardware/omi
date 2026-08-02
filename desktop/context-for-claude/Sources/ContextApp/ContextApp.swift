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

/// **Who asked this process to go away.**
///
/// Almost nothing in an app needs to know this. One thing does: the app may only resurrect itself
/// after a termination it did not ask for. `NSApplicationDelegate` is handed the same
/// `applicationWillTerminate` for a user pressing Quit and for macOS ending the process out from
/// under an onboarding run, and the two must not have the same answer — an app that comes back from
/// its own Quit is an app that cannot be quit, which is far worse than one that needs reopening.
///
/// So the origin is recorded at the *cause* rather than inferred at the effect. Every path in this
/// app that ends the process on the user's behalf says so here first; anything that arrives at
/// `applicationWillTerminate` without having said so was somebody else's decision.
@MainActor
enum TerminationOrigin {

    /// True when this process is ending because someone here asked it to.
    private(set) static var wasRequestedLocally = false

    /// The user pressed Quit. Call **before** `NSApp.terminate` — the delegate callback is
    /// synchronous with it, so a flag set afterwards is a flag set too late.
    static func userAskedToQuit() {
        wasRequestedLocally = true
        ContextLog.info("Quit requested by the user", "shell")
    }

    /// The Mac is logging out, restarting or shutting down.
    ///
    /// macOS quits every app the same way it quits us for a TCC change — a Quit Apple Event — so
    /// without this a log-out in the middle of onboarding would be answered by the app reopening
    /// itself into a session that is closing. Not a quit the *user* pressed, but just as much not
    /// ours to undo.
    static func systemIsPoweringOff() {
        wasRequestedLocally = true
        ContextLog.info("Power off in progress; this process will not reopen itself", "shell")
    }

    /// Puts the flag back to how a fresh process finds it.
    ///
    /// Nothing in the app calls this — a real process only ever ends once, so there is no un-asking.
    /// It exists because the test suite runs every case in a single process, and a case that leaves
    /// "the user pressed Quit" behind would silently pass the next case for the wrong reason: the
    /// one assertion here that has to be trusted is the one that says the app does *not* come back.
    static func resetForTesting() {
        wasRequestedLocally = false
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

        // A log-out, restart or shut-down quits every app the same way macOS quits us for a TCC
        // change — a Quit Apple Event — so `applicationWillTerminate` alone cannot tell the two
        // apart. This is the one notice macOS gives beforehand, and it is the difference between an
        // app that reopens itself into a closing session and one that goes quietly.
        NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.willPowerOffNotification, object: nil, queue: .main
        ) { _ in
            MainActor.assumeIsolated { TerminationOrigin.systemIsPoweringOff() }
        }

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
                    //
                    // This is also what the tutorial's timeline beat rides on: it observes the
                    // shortcut rather than opening anything itself, so the window the user learns to
                    // summon is opened here, by their own keypress, exactly as it will be forever
                    // after.
                    guard let store = Engine.shared.contextStore else { return }
                    RewindWindow.present(
                        store: store,
                        onOpenSettings: { SettingsWindow.present() },
                        // The tutorial's search beat rides on this the way the timeline beat rides on
                        // the shortcut above: the press falls straight through, the real bar opens
                        // because the user clicked the real pill, and the tutorial observes the panel
                        // that came up rather than taking the press.
                        //
                        // It used to `guard !Tutorial.searchPillWasPressed() else { return }` — the
                        // tutorial consumed the click and drew its own imitation of the results, so
                        // the one beat that teaches people to search was the one beat where searching
                        // did not open the search bar.
                        onSearch: { query in SearchBarWindow.present(prefill: query) })
                }
            }

            // …and "both rebindable" is only true because of this line. Settings' two recorders talk
            // to a `ShortcutBindingProvider`, and the one the window falls back to keeps its chords
            // in a dictionary that registers nothing — recording against it reports success and
            // changes no shortcut. Assigned here rather than inside `SettingsWindow` so it sits
            // beside `start(…)`: the same singleton that was just armed is the one the recorder
            // writes through, which is what makes a rebind take effect without a relaunch.
            SettingsWindow.shortcutProvider = LiveShortcutBindings()

            // Two reasons to open the card, and the second exists only because onboarding can end
            // this process on purpose: granting Screen Recording applies to the *next* launch, so
            // the flow restarts the app mid-run. The replacement has `context.onboarded` unset — the
            // run never finished — so the flag alone would have reopened it anyway; the resume point
            // is what stops it reopening at the cinematic, and it is consulted here too so a run in
            // progress is restored even if the flag had already been set.
            let onboarded = UserDefaults.standard.bool(forKey: Self.onboardedKey)
            if !onboarded || OnboardingResume().step != nil {
                OnboardingWindow.present()
            }
        }
    }

    /// Menu-bar-only: dismissing onboarding must never take the process with it.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    /// **Whether a process being terminated right now has to bring itself back.**
    ///
    /// Pure, and separated from every fact it depends on, because this is the decision with a wrong
    /// answer available in both directions and neither wrong answer is survivable:
    ///
    /// - Fail to revive and the user is where the bug report starts. macOS's own alert offers
    ///   **"Quit & Reopen"**, and measured on macOS 26.5.2 the reopen half simply does not happen for
    ///   this bundle. The live trace of the real incident: `Handling Quit AppleEvent` → `App
    ///   termination approved` → `Termination complete` → launchd `exited due to exit(0)`, and then
    ///   **not one further log line naming this bundle for the next five minutes** — no
    ///   LaunchServices open request, no runningboard launch job, not even a failed one. Nothing was
    ///   ever asked. AppKit's only contribution to the "Reopen" is
    ///   `_setShouldRestoreStateOnNextLaunch: 1`, which is state restoration *for whenever something
    ///   launches the app next* — and this app is `LSUIElement`, so there is no Dock icon, no
    ///   ⌘-Tab entry, and nothing for the user to click. The app is simply gone, mid-setup.
    /// - Revive too eagerly and the app cannot be quit. That is the worse failure, so every clause
    ///   below is a reason to stay dead and the default is to stay dead.
    ///
    /// **It cannot loop.** The replacement process starts *with* the Screen Recording grant, so
    /// `Permissions.screenGrantedAtLaunch` is true, which clears `screenPendingRelaunch`, which makes
    /// `screenNeedsRelaunch` false — the third argument is false in the process this one starts, so
    /// one revival is the most any grant can produce. And if the grant was revoked rather than given,
    /// `CGPreflightScreenCaptureAccess()` is false and `screenNeedsRelaunch` is false immediately.
    ///
    /// - Parameters:
    ///   - requestedLocally: the process is ending because something in this app asked it to — the
    ///     menu bar's Quit, or a power-off we were told about. Never resurrect one of those.
    ///   - onboardingInProgress: there is a card to come back to. A user who was not mid-setup has
    ///     nothing to lose by staying quit, and reopening on them would be the app refusing to leave.
    ///   - screenGrantPendingRelaunch: the Screen Recording grant is real but unusable until this
    ///     process is replaced — which is the only reason macOS ends us here in the first place.
    static func shouldReviveAfterTermination(
        requestedLocally: Bool,
        onboardingInProgress: Bool,
        screenGrantPendingRelaunch: Bool
    ) -> Bool {
        guard !requestedLocally else { return false }
        guard onboardingInProgress else { return false }
        return screenGrantPendingRelaunch
    }

    func applicationWillTerminate(_ notification: Notification) {
        // Closes the open session and writes a final heartbeat. Without this the last session stays
        // open forever and `status()` reports a recording that stopped hours ago.
        MainActor.assumeIsolated {
            // First, because it is the only thing here that has to survive the teardown going wrong.
            // The helper does not launch anything until this pid leaves the process table, so
            // spawning it before the shutdown work is safe and ordering-free — and a `pause()` that
            // hung would otherwise be the difference between the user getting their app back and not.
            reviveIfTheSystemEndedThisRun()

            // The tutorial owns borderless overlay windows and the menu-bar spotlight. Quitting
            // mid-walkthrough without tearing them down leaves them on screen with no process behind
            // them, which the user cannot dismiss.
            Tutorial.abandon()
            Engine.shared.pause()
        }
    }

    /// Leaves a relauncher behind when macOS is the one ending an onboarding run.
    ///
    /// The same detached helper the "Restart to finish" button uses — `Permissions.relaunchApp()`
    /// and this share `spawnRelaunchHelper()` precisely so there is one shell script in the product.
    /// The difference is who ends the process: there, we do; here, AppKit is already unwinding and
    /// all we may do is arrange for something that outlives us.
    @MainActor
    private func reviveIfTheSystemEndedThisRun() {
        guard
            Self.shouldReviveAfterTermination(
                requestedLocally: TerminationOrigin.wasRequestedLocally,
                onboardingInProgress: OnboardingResume().step != nil,
                screenGrantPendingRelaunch: Permissions.screenNeedsRelaunch)
        else { return }

        ContextLog.info(
            "Terminated mid-onboarding with a Screen Recording grant waiting on a relaunch; reopening",
            "shell")
        guard Permissions.spawnRelaunchHelper() else {
            // The process is going away either way — there is no staying up from inside
            // `applicationWillTerminate`. Record it: the user is about to find the app gone with no
            // Dock icon to bring it back, and that is exactly the shape of the original report.
            ContextTelemetry.recordFallback(
                area: .settings, from: "revive-after-system-quit", to: "stay-quit",
                reason: "helper-spawn-failed", outcome: .degraded)
            return
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
