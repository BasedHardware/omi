import AppKit
import ContextCore
import CoreText
import SwiftUI

/// Context for Claude's entire scene graph: one menu bar item, one popover, and the application menu
/// that comes with having a Dock icon.
///
/// There is deliberately no `WindowGroup`. Onboarding, the timeline, search and Settings are each an
/// AppKit window owned by their own type rather than a SwiftUI scene — so a scene here would only
/// ever be an empty window the user could summon by accident.
///
/// **The app is no longer `LSUIElement`.** It ships with a Dock icon by default and `DockPresence`
/// is the row that takes it away again; `Resources/Info.plist` carries the reasoning for why the
/// plist declares the majority shape rather than the app promoting itself into it. What changes up
/// here is that "a scene the user could summon by accident" stopped being hypothetical: a regular
/// app *draws* its main menu, so the two standard items below had to be pointed at this app's real
/// surfaces rather than left aimed at a placeholder scene and a bare `terminate`.
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
        // unaided, which is what an app whose windows are all AppKit's wants.
        Settings { EmptyView() }
            .commands {
                // **The two standard items that would otherwise do the wrong thing.**
                //
                // Both were invisible while the app was `.accessory` — an accessory app draws no
                // menu bar, so whatever SwiftUI built for it sat there unseen. A regular app draws
                // it, which turns two latent defects into two the user can click.
                //
                // `Settings…` is the plainer of the two, and the sharper. The scene above exists
                // only because a SwiftUI `App` must have one; the app's real Settings is
                // `SettingsWindow`, hand-built in AppKit. Left alone, ⌘, opens `EmptyView` in a
                // window called Settings — the exact "empty window the user could summon by
                // accident" the header above says there must not be. Replacing the group is what
                // removes SwiftUI's own item rather than sitting a second one beside it.
                CommandGroup(replacing: .appSettings) {
                    Button("Settings…") { SettingsWindow.present() }
                        .keyboardShortcut(",", modifiers: .command)
                }

                // …and `Quit` is the one with teeth. A bare `NSApp.terminate` reaches
                // `applicationWillTerminate` with nothing having recorded *who asked*, which is
                // exactly the input `shouldReviveAfterTermination` refuses to guess at: a user who
                // presses ⌘Q during onboarding would be read as macOS having ended the run, and the
                // app would spawn its own replacement. An app that cannot be quit is the failure
                // that file calls worse than an app that needs reopening. The menu bar's Quit has
                // always said so first (`StatusView`); this is the same two lines, in the order they
                // have to be in, for the menu a Dock icon comes with.
                CommandGroup(replacing: .appTermination) {
                    Button("Quit Context for Claude") {
                        TerminationOrigin.userAskedToQuit()
                        NSApp.terminate(nil)
                    }
                    .keyboardShortcut("q", modifiers: .command)
                }
            }
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
        // `milestone`, not `info`: "did the app come back, and if not why not" is answered from the
        // log days later, and `info` is gone within minutes. See `ContextLog`.
        ContextLog.milestone("Quit requested by the user", "shell")
    }

    /// The Mac is logging out, restarting or shutting down.
    ///
    /// macOS quits every app the same way it quits us for a TCC change — a Quit Apple Event — so
    /// without this a log-out in the middle of onboarding would be answered by the app reopening
    /// itself into a session that is closing. Not a quit the *user* pressed, but just as much not
    /// ours to undo.
    static func systemIsPoweringOff() {
        wasRequestedLocally = true
        ContextLog.milestone("Power off in progress; this process will not reopen itself", "shell")
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

/// **How many times this install is allowed to bring itself back, and how recently.**
///
/// The revival predicate used to be unable to loop by construction: its third clause was "a Screen
/// Recording grant is waiting on a relaunch", and a process that launches *with* the grant reports
/// false, so one grant bought exactly one revival. That clause is gone — it was answering the wrong
/// question and it cost the user their app (see `ContextAppDelegate.shouldReviveAfterTermination`)
/// — and with it went the proof that the chain terminates.
///
/// So the ceiling is explicit now rather than emergent. An app that respawns itself forever is the
/// one failure worse than an app that needs reopening, and "it cannot happen because of how this
/// unrelated permission flag works" is not a property anybody can maintain.
///
/// The window matters as much as the count. A user who grants two permissions in a row legitimately
/// gets quit twice inside a minute; a bug that respawns on a loop does it hundreds of times. Three
/// inside ten minutes separates those without a clock deciding anything the user did not.
///
/// Deliberately not `@MainActor`: `UserDefaults` is thread-safe and the predicate that consults the
/// allowance is a pure function anything may call.
struct RevivalBudget {

    /// Namespaced with the app's other `context.*` defaults.
    static let key = "context.revival.recentAt"

    /// How far back a revival still counts against the next one.
    static let window: TimeInterval = 10 * 60

    /// How many revivals that window may contain before the app stays quit.
    static let allowance = 3

    private let defaults: UserDefaults

    init(defaults: UserDefaults = .standard) {
        self.defaults = defaults
    }

    /// The revivals still inside the window, oldest first.
    func recent(now: Double = ContextTime.now) -> [Double] {
        Self.inWindow(defaults.array(forKey: Self.key) as? [Double] ?? [], now: now)
    }

    /// Spends one, **now**, and writes it where the successor process will find it.
    ///
    /// `synchronize()` is deprecated and used on purpose: the only caller is
    /// `applicationWillTerminate`, and the successor is launched by a helper that starts the moment
    /// this pid leaves the process table. The ordinary periodic flush is not fast enough to be
    /// certain the replacement reads a budget that includes this revival, and a budget the successor
    /// cannot see is not a ceiling at all.
    func record(now: Double = ContextTime.now) {
        var kept = recent(now: now)
        kept.append(now)
        // Bounded: never store more than the window's worth plus the one that just happened.
        defaults.set(Array(kept.suffix(Self.allowance + 1)), forKey: Self.key)
        defaults.synchronize()
    }

    /// Pure, so the arithmetic can be asserted without a process ending.
    ///
    /// `abs` rather than a one-sided comparison: a clock that moved backwards would otherwise leave
    /// stamps in the future that never expire and never count, which is a ceiling that silently
    /// stops being one. Counting them errs towards staying quit, and staying quit is the safe
    /// direction for every clause of this decision.
    static func inWindow(_ stamps: [Double], now: Double) -> [Double] {
        stamps.filter { abs(now - $0) < window }
    }
}

/// Everything that must happen once per process, in the order the rest of the app assumes:
/// activation policy before any window can steal focus, fonts before anything draws, capture before
/// the user can look at its status, onboarding last.
final class ContextAppDelegate: NSObject, NSApplicationDelegate {
    /// Set by the onboarding flow once the user has finished it.
    private static let onboardedKey = "context.onboarded"

    func applicationDidFinishLaunching(_ notification: Notification) {
        // **The Dock icon, settled before anything can draw.**
        //
        // `Resources/Info.plist` launches this process `.regular`, so by the time this line runs the
        // icon is already in the Dock and macOS has built the app's main menu around it. All this
        // does is honour a user who turned the row off, and it happens here — first, ahead of the
        // status item, the engine and onboarding — because an activation policy applied after a
        // window has been ordered in is a window that has already taken focus under the old shape.
        //
        // It reads the stored default through `DockPresence` rather than touching
        // `SettingsStore.shared`, which would build the whole preference store and install an
        // appearance on `NSApp` this early for the sake of one boolean. Both paths go through the
        // same key and the same mapping, which is the only thing that keeps the row's meaning at
        // launch identical to its meaning on click.
        //
        // This was an unconditional `.accessory`, on the reasoning that a Dock icon is "the single
        // most visible way this product could stop being ambient". That is half of a real trade: the
        // other half is a 16 pt template mark lost among thirty menu-bar extras, which is the report
        // that reversed it. An app nobody can find is not ambient either.
        NSApp.setActivationPolicy(DockPresence.launchPolicy())

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

            // After the engine, because an updater is worth nothing next to a capture that never
            // started — and because this line is a no-op on most machines that run it. The policy
            // refuses any bundle whose signature carries no Team ID, which is every local build, so
            // only a Developer ID build with a real public key ever reaches a feed.
            ContextUpdater.shared.start()

            // Decode the four onboarding cues now so the first one does not pay for it mid-beat.
            // Safe with the assets missing: the layer degrades to silence rather than throwing,
            // because nothing about onboarding may depend on audio succeeding.
            Sound.prepare()

            // Both Command keys together open the timeline, double-tap Command-Shift opens search.
            // Both are
            // rebindable, and both simply do not fire while Accessibility is ungranted — a global
            // monitor cannot see keys without it, and pretending to be armed would be worse.
            GlobalShortcuts.shared.start { action in
                switch action {
                case .openSearch:
                    SearchBarWindow.toggle()
                case .openTimeline:
                    // This is also what the tutorial's timeline beat rides on: it observes the
                    // shortcut rather than opening anything itself, so the window the user learns to
                    // summon is opened here, by their own keypress, exactly as it will be forever
                    // after.
                    Self.openTimeline()
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

    /// The app's job is done with nothing on screen, so closing the last window is not a quit —
    /// dismissing onboarding never was, and now that there is a Dock icon, closing the timeline must
    /// not be either.
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    /// **What the Dock icon does when it is clicked.**
    ///
    /// The whole point of having one is that the app can be found without hunting the menu bar, and
    /// an icon that answers a click with nothing on screen is not findable, it is broken. macOS
    /// sends this for a Dock click, an `open -a`, and a Finder double-click of a bundle that is
    /// already running — every "I want that app" gesture that is not the status item.
    ///
    /// Returning `true` rather than `false`: this handles the *summoning*, and AppKit still owns the
    /// rest of a reopen — un-minimising a window the user had put in the Dock is its half, and
    /// nothing here duplicates it.
    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows: Bool) -> Bool {
        MainActor.assumeIsolated { Self.surfaceSomethingForTheUser(hasVisibleWindows: hasVisibleWindows) }
        return true
    }

    /// The one place that decides *which* surface a "show me the app" gesture means.
    ///
    /// Ordered by what the user is in the middle of, not by what is most impressive:
    ///
    /// - **An unfinished setup outranks everything.** The card is a floating window that steps aside
    ///   while System Settings is frontmost (`Permissions.systemSettingsIsFrontmost`) and that the
    ///   flow itself hides between beats, so "there is no card on screen" is a routine state of a run
    ///   that is very much in progress. Opening a timeline over it would bury the one thing the user
    ///   still has to finish; `OnboardingWindow.present()` brings back the run they were in.
    /// - **Something already up is enough.** AppKit brings the app's windows forward on a reopen by
    ///   itself. A second window ordered in on top of that is the Dock icon opening a timeline over
    ///   the Settings sheet the user was reading.
    /// - **Otherwise the timeline**, which is this app's one real window: the whole capture record,
    ///   with search and Settings reachable from inside it.
    @MainActor
    private static func surfaceSomethingForTheUser(hasVisibleWindows: Bool) {
        let onboarded = UserDefaults.standard.bool(forKey: onboardedKey)
        if !onboarded || OnboardingResume().step != nil {
            OnboardingWindow.present()
            return
        }

        guard !hasVisibleWindows else { return }

        openTimeline()
    }

    /// The timeline, opened the one way it is ever opened.
    ///
    /// Lifted out of the shortcut handler when the Dock icon became a second caller, and `static` so
    /// neither caller has to capture the delegate. The two hand-offs it installs are not incidental —
    /// they are what makes the window behave, and a second call site that reconstructed them by hand
    /// is how one of the two quietly stops being passed.
    @MainActor
    private static func openTimeline() {
        // The store opens lazily on the engine's own queue, so ask at open time rather than at
        // launch. Nil means it is not open yet: decline to put a timeline over nothing instead of
        // showing an empty one. That answer is worth keeping even though it makes a Dock click do
        // nothing for the second or two after launch during which it can be true — an empty timeline
        // claiming the user has no history is a worse first impression than a click that waits.
        guard let store = Engine.shared.contextStore else {
            ContextLog.info("timeline asked for before the store was open; nothing shown", "shell")
            return
        }

        RewindWindow.present(
            store: store,
            onOpenSettings: { SettingsWindow.present() },
            // The tutorial's search beat rides on this the way the timeline beat rides on the
            // shortcut: the press falls straight through, the real bar opens because the user
            // clicked the real pill, and the tutorial observes the panel that came up rather than
            // taking the press.
            //
            // It used to `guard !Tutorial.searchPillWasPressed() else { return }` — the tutorial
            // consumed the click and drew its own imitation of the results, so the one beat that
            // teaches people to search was the one beat where searching did not open the search bar.
            onSearch: { query in SearchBarWindow.present(prefill: query) })
    }

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
    ///   launches the app next* — and this app was `LSUIElement` when that was measured, so there
    ///   was no Dock icon, no ⌘-Tab entry, and nothing for the user to click. The app is simply
    ///   gone, mid-setup.
    ///
    ///   **The Dock icon softens that and does not remove it, so none of this is relaxed.** A Dock
    ///   icon belongs to a *running* app unless the user has kept it in the Dock, and the run this
    ///   is about is one that ended during onboarding — before anybody has thought about keeping
    ///   anything. The "Show Dock Icon" row also puts the process back into exactly the shape the
    ///   incident was measured in, on one click, for good.
    /// - Revive too eagerly and the app cannot be quit. That is the worse failure, so every clause
    ///   below is a reason to stay dead and the default is to stay dead.
    ///
    /// **This shipped once already, gated on the wrong permission, and the user lost their app
    /// again.** The third clause used to be "a Screen Recording grant is waiting on a relaunch",
    /// on the reasoning that Screen Recording is the only grant that needs a new process. It is not
    /// the only grant that makes macOS *quit* one. From the live trace of the second failure:
    ///
    /// ```text
    /// 14:07:49.825  SecurityPrivacyExtension  kTCCServiceAccessibility  com.omi.context-for-claude  full
    /// 14:07:49.828  SecurityPrivacyExtension  kTCCServiceScreenCapture  com.omi.context-for-claude  none
    /// 14:07:51.267  SecurityPrivacyExtension  AESendMessage(aevt,quit target='kpid'[pid=13102 …
    /// 14:07:51.280  Context for Claude        [AppKit:Application] Handling Quit AppleEvent
    /// 14:07:51.325  launchservicesd           QUITTING: pid=13102
    /// ```
    ///
    /// …and the next launch of this bundle is at **14:08:16**, twenty-five seconds later, which is
    /// the user reopening it by hand. The alert they pressed "Quit & Reopen" on was the
    /// **Accessibility** one. Screen Recording was `none` — never granted — so the old third clause
    /// was false, the helper was never spawned, and the app stayed dead in exactly the way the fix
    /// was supposed to have ended.
    ///
    /// So the gate no longer names a permission. It cannot: macOS raises that alert for any TCC
    /// service whose change a running process cannot pick up, the app has four of them on one card,
    /// and a predicate that has to enumerate which of macOS's alerts it believes in will keep being
    /// wrong in the same direction. What is actually true at this moment is smaller and knowable:
    /// **somebody other than the user ended a run that had not finished.**
    ///
    /// - Parameters:
    ///   - requestedLocally: the process is ending because something in this app asked it to — the
    ///     menu bar's Quit, or a power-off we were told about. Never resurrect one of those. This is
    ///     the clause that keeps the app quittable and it is not negotiable against any of the rest.
    ///   - onboardingInProgress: there is a card to come back to. A user who has finished setup has
    ///     nothing to lose by staying quit, and reopening on them would be the app refusing to leave.
    ///     It also bounds the blast radius of the widened gate: outside the one flow that macOS ends
    ///     on purpose, nothing here reopens anything.
    ///   - revivalsAlreadySpent: how many times this install has already brought itself back inside
    ///     `RevivalBudget.window`. The old shape could not loop by accident of how a permission flag
    ///     worked; this one says so out loud, because an app that respawns forever is worse than an
    ///     app that needs reopening and that has to be guaranteed by the predicate rather than by a
    ///     neighbouring subsystem.
    static func shouldReviveAfterTermination(
        requestedLocally: Bool,
        onboardingInProgress: Bool,
        revivalsAlreadySpent: Int
    ) -> Bool {
        guard !requestedLocally else { return false }
        guard onboardingInProgress else { return false }
        return revivalsAlreadySpent < RevivalBudget.allowance
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
        let requestedLocally = TerminationOrigin.wasRequestedLocally
        let onboardingInProgress = OnboardingResume().step != nil
        let budget = RevivalBudget()
        let spent = budget.recent().count
        let revive = Self.shouldReviveAfterTermination(
            requestedLocally: requestedLocally,
            onboardingInProgress: onboardingInProgress,
            revivalsAlreadySpent: spent)

        // **Every input and the answer, at a level that is still readable tomorrow.**
        //
        // The first version of this fix logged only the yes branch, and at `info` — which unified
        // logging keeps in memory and throws away within minutes. When it failed for the user the
        // second time there was nothing to read: `log show` over the whole window returned the
        // app's errors and not one line about the decision that had just been made. Working out
        // that Screen Recording had been `none` all along took a system-wide trace of
        // `SecurityPrivacyExtension`. That is the diagnosis this line exists to hand over instead.
        //
        // `screenNeedsRelaunch` is reported and no longer consulted. It is included precisely
        // because it is the thing that was silently false: seeing it next to the answer is what
        // makes the next report readable in one query. Reading it also still writes the pending
        // flag the successor process wants, which is why it is called rather than guessed at.
        ContextLog.milestone(
            "Termination — requestedLocally=\(requestedLocally) "
                + "onboardingInProgress=\(onboardingInProgress) "
                + "revivalsSpent=\(spent)/\(RevivalBudget.allowance) "
                + "screenPendingRelaunch=\(Permissions.screenNeedsRelaunch) "
                + "→ \(revive ? "reopening this bundle" : "staying quit")",
            "shell")

        guard revive else { return }

        // Spent before the helper is asked for, and flushed synchronously. A successor that reads a
        // budget without this revival in it is a successor with a fresh allowance, which is the
        // fork bomb the ceiling exists to prevent.
        budget.record()

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
