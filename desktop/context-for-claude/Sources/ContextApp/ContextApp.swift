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
                    Button("Settings…") { SettingsWindow.present(via: .shortcut) }
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

    /// This app is restarting itself and has **already** arranged for the replacement.
    ///
    /// Not "the user pressed Quit", though it sets the same flag, and the distinction is worth a
    /// name: what the delegate needs to know is that a successor is already spoken for. Unmarked,
    /// `Permissions.relaunchApp()` would reach `applicationWillTerminate` looking exactly like the
    /// termination `shouldReviveAfterTermination` exists to undo — a quit nobody here asked for,
    /// moments after a permission landed — and the app would spawn a second relaunch helper on top
    /// of the one it had just spawned, spending a revival from the budget for it.
    static func relaunchWasArrangedHere() {
        wasRequestedLocally = true
        ContextLog.milestone("Restarting: a relaunch helper is already up for this bundle", "shell")
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

/// **The surface a launch, or a Dock click, has to put in front of the user.**
///
/// Three cases because there are three flows a user can be in the middle of, and the whole content of
/// the type is that they are mutually exclusive and ordered — see `ContextAppDelegate.landing`.
enum LaunchLanding: Equatable {
    /// Setup was never finished, or a run of it is still open.
    case onboarding
    /// A walkthrough was interrupted, at this beat.
    case tutorial(TutorialStep)
    /// Nothing is outstanding: the app's own surface.
    case activity
}

/// Everything that must happen once per process, in the order the rest of the app assumes:
/// activation policy before any window can steal focus, fonts before anything draws, capture before
/// the user can look at its status, onboarding last.
final class ContextAppDelegate: NSObject, NSApplicationDelegate {
    /// Set by the onboarding flow once the user has finished it, and cleared only by
    /// `OnboardingReset` — Settings' "Run setup again", which puts the install back to a first run.
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
            // **What this process was allowed to do when it started**, recorded before any surface
            // exists to change it. `shouldReviveAfterTermination` asks whether a grant arrived
            // *during* the run, and a change needs something to be a change from. Ahead of
            // `Engine.start()` because the engine's own capability poll short-circuits — see
            // `Permissions.noteGrantsAtLaunch()`.
            Permissions.noteGrantsAtLaunch()

            // Immediately after the grant snapshot and before anything else can act on it, because
            // `start()` decides first-launch from a `UserDefaults` key that onboarding also writes:
            // reaching it second would report every install as a returning one.
            ContextAnalytics.start()
            ContextAnalytics.recordPermissionSnapshot()

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

            // Both are rebindable, and both simply do not fire while Accessibility is ungranted — a
            // global monitor cannot see keys without it, and pretending to be armed would be worse.
            // What each one does is `shortcutFired`; the toggle it acts on is built here, once, so
            // the mapping below never has to know how to find a window.
            GlobalShortcuts.shared.start { action in
                // The chord and a recorded key are the same press to this closure and two different
                // routes to the person making it: one is the gesture the product teaches, the other
                // is a shortcut they chose. `binding(for:)` is the only thing that can tell them
                // apart, and it lives out here rather than inside the toggle so the window stays a
                // parameter — see `shortcutFired`.
                let via: AnalyticsEvent.OpenSource
                switch GlobalShortcuts.shared.binding(for: action) {
                case .gestureDefault: via = .gesture
                case .recorded: via = .shortcut
                }
                Self.shortcutFired(action, on: SearchBarWindow.hotkeyToggle(via: via))
            }

            // …and "both rebindable" is only true because of this line. Settings' two recorders talk
            // to a `ShortcutBindingProvider`, and the one the window falls back to keeps its chords
            // in a dictionary that registers nothing — recording against it reports success and
            // changes no shortcut. Assigned here rather than inside `SettingsWindow` so it sits
            // beside `start(…)`: the same singleton that was just armed is the one the recorder
            // writes through, which is what makes a rebind take effect without a relaunch.
            SettingsWindow.shortcutProvider = LiveShortcutBindings()

            // What a launch puts on screen is the same question the Dock icon asks, so it is asked
            // in the same place — see `surfaceSomethingForTheUser`.
            Self.surfaceSomethingForTheUser()
        }
    }

    /// **What a global shortcut does**, as a function of the chord and the window it toggles.
    ///
    /// **There is one chord and it reaches the Activity panel.** Both Command keys together is this
    /// app's advertised way in, and what a way in has to land on is the surface the app opens on —
    /// Activity. It used to land on the timeline, from when the timeline *was* the app's one real
    /// window; leaving it there would have made the gesture the product teaches the one gesture that
    /// does not take you to the app. There was a second chord, `openSearch`, and it arrived here to
    /// do the identical thing — two recorders, two defaults and two conflict rows over one
    /// `window.press()`. It is gone; see `GlobalShortcuts.Action`.
    ///
    /// **It toggles, and that is the reported fix rather than a tidy-up.** `openActivity` called
    /// `present`, on the reasoning that a launch and a Dock click must never close anything — true, and
    /// not a fact about a *keystroke*: *"Every window that gets launched by a hotkey should also be
    /// dismissed by the same hotkey, right now I have no way to exit this without clicking X."* So the
    /// distinction moved to where it belongs. This is the keyboard, and it toggles; `openActivities()`
    /// is what launch, the Dock icon and the menu row still call, and it still only ever opens. A window
    /// behind another application comes forward rather than closing (`HotkeyToggle`), so a second press
    /// is never a keystroke with nothing to show for it.
    ///
    /// The tutorial's chord beat rides on this: it observes the shortcut rather than opening anything
    /// itself, so the window the user learns to summon is opened here, by their own keypress, exactly as
    /// it will be forever after.
    ///
    /// Named and `static` rather than left inline in `start(onTrigger:)`, because that is where the
    /// defect could hide: a mapping written into a closure inside `applicationDidFinishLaunching` is one
    /// nothing can ask what it does with a *second* press. The window arrives as a parameter for the
    /// same reason — pressing the real one from a test process would put a floating panel on screen.
    ///
    /// One case for both, and adding a third action still fails to compile here, which is the property
    /// worth keeping: a new shortcut must not silently inherit this window.
    @MainActor
    @discardableResult
    static func shortcutFired(_ action: GlobalShortcuts.Action, on window: HotkeyToggle) -> HotkeyPress {
        // Recorded here rather than inside `GlobalShortcuts` because this is where a press becomes a
        // press that *did* something. The monitor also fires on chords the app decided not to act
        // on, and counting those would report a gesture as working on machines where it does not.
        ContextAnalytics.record(.gestureFired)
        switch action {
        case .openActivity:
            return window.press()
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
        MainActor.assumeIsolated { Self.surfaceSomethingForTheUser(via: .reopen) }
        return true
    }

    /// **What the user is in the middle of**, as a value rather than as a branch.
    ///
    /// Pure, and separated from the three facts it reads, for the same reason
    /// `shouldReviveAfterTermination` is: the ordering is the whole decision, and an ordering that
    /// can only be exercised by launching the app is an ordering nobody can assert.
    ///
    /// The order, and why it is this one:
    ///
    /// 1. **An unfinished setup outranks everything.** The card is a floating window that steps aside
    ///    while System Settings is frontmost (`Permissions.systemSettingsIsFrontmost`) and that the
    ///    flow itself hides between beats, so "there is no card on screen" is a routine state of a run
    ///    that is very much in progress. It also comes first because the walkthrough is something
    ///    onboarding *hands off to* — its last card seals the run before starting it — so a machine
    ///    carrying both records is one where the earlier flow never finished, and finishing it is the
    ///    only order that ends with both records spent.
    /// 2. **A walkthrough in progress outranks the Activity panel**, exactly as an unfinished
    ///    onboarding does, and for a sharper reason than "the card would be buried". The panel *is*
    ///    the surface two of the tutorial's beats are about: `findMoments` waits for one to appear
    ///    and advances the moment it does. A launch that opened Activity and then resumed the run
    ///    would satisfy that beat on the user's behalf — the flow would credit them with a press they
    ///    never made, which is the one thing `TutorialModel`'s rules exist to prevent. So this is an
    ///    `else`, not a second thing to do.
    /// 3. **Otherwise the Activity panel**, always. It used to open on nothing at all, which was
    ///    defensible while every surface was summoned by a chord and is not now that there is a Dock
    ///    icon: an app that launches to an empty screen has not launched. Deliberately not gated on
    ///    the capture database being open — the store opens lazily and the surface waits for it,
    ///    rather than the launch waiting for the surface (see `SearchResultsModel`).
    static func landing(
        onboarded: Bool, onboardingInProgress: Bool, tutorialResume: TutorialStep?
    ) -> LaunchLanding {
        if !onboarded || onboardingInProgress { return .onboarding }
        if let beat = tutorialResume { return .tutorial(beat) }
        return .activity
    }

    /// The one place that decides *which* surface a "show me the app" gesture means, and the one
    /// place that reads the records behind it.
    ///
    /// Launch and the Dock icon both arrive here. They used to answer the question separately, with
    /// launch carrying its own copy of the onboarding clause — one owner is what stops the two
    /// drifting the moment a third flow (this walkthrough) needs a place in the order.
    ///
    /// **`hasVisibleWindows` used to gate the last clause and no longer does, and that is the fix
    /// rather than an oversight.** The reasoning was "AppKit brings the app's windows forward by
    /// itself, so a second window ordered in on top is the Dock icon opening a timeline over the
    /// Settings sheet the user was reading". It stopped being true the moment the target became the
    /// surface this gesture *means*: with any window at all on screen — the timeline, Settings, a
    /// minimised anything — a Dock click did nothing whatsoever, which is the definition of an app
    /// that cannot be found. `SearchBarWindow.present()` is idempotent and brings the panel forward,
    /// so the answer to "show me the app" is the same surface every time.
    ///
    /// **A third caller joined launch and the Dock icon**: `OnboardingReset.restart()`, which spends
    /// the records this reads and then asks the same question a first launch asks. It is not private
    /// for that reason alone — a reset that opened `OnboardingWindow` itself would be a second opinion
    /// about what an un-onboarded install shows, and the first flow to earn a place in `landing` would
    /// find only one of the two updated.
    ///
    /// - Parameter via: how the app was asked for. `.launch` is the default because two of the three
    ///   callers are one — a process starting, and a reset that puts the install back to a first run
    ///   — and only the Dock icon is the other, which says so.
    @MainActor
    static func surfaceSomethingForTheUser(via: AnalyticsEvent.OpenSource = .launch) {
        switch landing(
            onboarded: UserDefaults.standard.bool(forKey: onboardedKey),
            onboardingInProgress: OnboardingResume().step != nil,
            tutorialResume: TutorialResume().step)
        {
        case .onboarding:
            OnboardingWindow.present()
        case .tutorial(let beat):
            // Idempotent on a run that is already walking: `TutorialController.start` brings the
            // current card back rather than starting a second machine, which is what a Dock click
            // mid-walkthrough should do and is the reason this clause is not gated on the tutorial
            // being stopped.
            Tutorial.start(resumingAt: beat)
        case .activity:
            openActivities(via: via)
        }
    }

    /// **The Activity panel**, opened the one way it is ever opened.
    ///
    /// What "show me the app" means: launch, the Dock icon and the menu bar's row all arrive here.
    /// `present` and never `toggle`: none of these three is a keystroke a user repeats, and a Dock
    /// click that closed the panel would be a gesture that does the opposite of what it says.
    ///
    /// **The ⌘ + ⌘ chord used to arrive here and deliberately no longer does.** A keystroke *is*
    /// repeated, and one that could only ever open left the panel with no way off the keyboard — see
    /// the shortcut handler above. The chord toggles; these three do not.
    ///
    /// No store guard, unlike `openTimeline` below. The surface asks for the capture database on
    /// every read and waits for it to open, so there is nothing to decline over — and a launch that
    /// showed nothing for the second or two before the store opens would be exactly the inert gesture
    /// this panel exists to stop.
    @MainActor
    private static func openActivities(via: AnalyticsEvent.OpenSource) {
        SearchBarWindow.present(via: via)
    }

    /// The timeline, opened the one way it is ever opened.
    ///
    /// `static` so no caller has to capture the delegate. The two hand-offs it installs are not
    /// incidental — they are what makes the window behave, and a second call site that reconstructed
    /// them by hand is how one of the two quietly stops being passed.
    ///
    /// **Not `private`, since the chord stopped being the caller.** Repointing `openActivity` at the
    /// main window left this with no call site inside the shell, and the honest answer to that is not
    /// to delete it: the menu bar's "Open Timeline" row is now the app's route to this window, and it
    /// had a hand-rolled copy of exactly the reconstruction the note above warns about. One owner,
    /// called from there.
    ///
    /// - Parameter via: which of this window's routes was taken — the menu bar's row, the search
    ///   panel's Timeline pill, or the tutorial. It is threaded through rather than reported at the
    ///   two call sites for the same reason the hand-offs are constructed here: a third route would
    ///   otherwise arrive with the second one's label on it.
    @MainActor
    static func openTimeline(via: AnalyticsEvent.OpenSource) {
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
            via: via,
            onOpenSettings: { SettingsWindow.present(via: .inAppPill) },
            // The "Search All" pill brings the main window forward with the timeline's query in it.
            // The tutorial's search beat rides on this the way the timeline beat rides on the
            // shortcut: the press falls straight through, the real window comes forward because the
            // user clicked the real pill, and the tutorial observes the ask rather than taking it.
            //
            // It used to `guard !Tutorial.searchPillWasPressed() else { return }` — the tutorial
            // consumed the click and drew its own imitation of the results, so the one beat that
            // teaches people to search was the one beat where searching did not open the search bar.
            onSearch: { query in SearchBarWindow.present(via: .inAppPill, prefill: query) })
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
    /// **somebody other than the user ended a run that had not finished** — or, since the third
    /// report, ended a finished one the instant a permission landed in it. See the `aGrantJustArrived`
    /// parameter for why that second half had to be added and why it is a grant *arriving* rather
    /// than the far easier "somebody other than the user ended us".
    ///
    /// - Parameters:
    ///   - requestedLocally: the process is ending because something in this app asked it to — the
    ///     menu bar's Quit, or a power-off we were told about. Never resurrect one of those. This is
    ///     the clause that keeps the app quittable and it is not negotiable against any of the rest.
    ///   - onboardingInProgress: there is a card to come back to. A user who has finished setup has
    ///     nothing to lose by staying quit, and reopening on them would be the app refusing to leave.
    ///     It also bounds the blast radius of the widened gate: outside the one flow that macOS ends
    ///     on purpose, nothing here reopens anything.
    ///   - aGrantJustArrived: a capability this process could not use has become one it can, within
    ///     the last couple of minutes. **This is the third failure, and it is the same failure a
    ///     third time.** The clause above bounded the revival to an unfinished run, on the reasoning
    ///     that "outside the one flow macOS ends on purpose, nothing here reopens anything" — and
    ///     macOS does not restrict itself to that flow. From the live trace of the third report, a
    ///     user who had finished setup months of use ago went to Privacy & Security to turn a stale
    ///     switch off and on again, which is the remedy this app's own `staleGrantReason` tells them
    ///     to use:
    ///
    ///     ```text
    ///     11:40:09  tccd                SecurityPrivacyExtension pid=9049 — the Privacy pane
    ///     11:40:11  Context for Claude  Handling Quit AppleEvent
    ///     11:40:11  Context for Claude  Termination — requestedLocally=false
    ///                                   onboardingInProgress=false … → staying quit
    ///     ```
    ///
    ///     Reported as *"the app crashes upon giving permissions"*, and it is not a crash: there is
    ///     no `.ips` report anywhere, and the exit is a clean one. The app simply granted the user's
    ///     wish by disappearing — capture stopped, silently, at the exact moment the user had just
    ///     told it to start.
    ///
    ///     So the second clause is an `||` rather than a widening. `requestedLocally == false` on
    ///     its own would have covered this and must not be used: measured in this app's own log, an
    ///     ordinary Sparkle update is also an external quit, and reviving one of those would race
    ///     the relaunch the updater is already performing. A grant *arriving* is the fact that is
    ///     true of macOS's TCC recycle and of nothing else — see `Permissions.aGrantJustArrived()`,
    ///     which also explains why a grant being *revoked* is pointedly not this.
    ///   - revivalsAlreadySpent: how many times this install has already brought itself back inside
    ///     `RevivalBudget.window`. The old shape could not loop by accident of how a permission flag
    ///     worked; this one says so out loud, because an app that respawns forever is worse than an
    ///     app that needs reopening and that has to be guaranteed by the predicate rather than by a
    ///     neighbouring subsystem.
    /// **Whether there is an unfinished run to come back to** — the second clause of the decision
    /// below, and no longer a question with one flow in it.
    ///
    /// Pure, and separate, because the answer changed while the predicate's parameter name did not.
    /// `shouldReviveAfterTermination` calls it `onboardingInProgress` from when onboarding was the
    /// only flow that macOS could end mid-run; what it has always meant is *there is something to
    /// come back to*. The walkthrough is now the flow that most needs it: `TutorialStep.screenAccess`
    /// asks for Screen Recording after onboarding's last card has already sealed its own books
    /// (`OnboardingView.sealTheRun`), so the "Quit & Reopen" this whole mechanism was measured
    /// against arrives with `OnboardingResume` spent — and the app stayed dead in exactly the shape
    /// of the original report, one flow later.
    ///
    /// Neither record means "the user is looking at a card right now". Both mean the run was never
    /// concluded, which is the same thing the revival is for: `TutorialModel.abandon` deliberately
    /// leaves its record behind when the process is torn down under a run that was still going.
    static func aRunIsWaiting(
        onboardingResume: OnboardingStep?, tutorialResume: TutorialStep?
    ) -> Bool {
        onboardingResume != nil || tutorialResume != nil
    }

    static func shouldReviveAfterTermination(
        requestedLocally: Bool,
        onboardingInProgress: Bool,
        aGrantJustArrived: Bool,
        revivalsAlreadySpent: Int
    ) -> Bool {
        guard !requestedLocally else { return false }
        guard onboardingInProgress || aGrantJustArrived else { return false }
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
        // **There are two unfinished runs now, and the second one is the one that asks macOS for
        // this quit.** The parameter is named for onboarding because onboarding was the only flow
        // that existed when the predicate was written; what it has always meant is "there is
        // something to come back to". `TutorialStep.screenAccess` calls
        // `CGRequestScreenCaptureAccess` after onboarding has sealed its own books, so a walkthrough
        // hits exactly the alert this whole mechanism was measured against — with `OnboardingResume`
        // already spent, and therefore, until this line, with the app staying dead.
        let tutorialBeat = TutorialResume().step
        let onboardingInProgress = Self.aRunIsWaiting(
            onboardingResume: OnboardingResume().step, tutorialResume: tutorialBeat)
        // **The clause that covers a run with nothing waiting in it.** Re-reads every capability
        // rather than trusting the last poll: the quit follows the switch by a second or two and the
        // engine's poll runs every thirty, so on the reported timeline nothing had looked since
        // before the grant existed.
        let grantJustArrived = Permissions.aGrantJustArrived()
        let budget = RevivalBudget()
        let spent = budget.recent().count
        let revive = Self.shouldReviveAfterTermination(
            requestedLocally: requestedLocally,
            onboardingInProgress: onboardingInProgress,
            aGrantJustArrived: grantJustArrived,
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
                // Which of the two unfinished runs, when it is the walkthrough. Same argument as
                // every other field on this line: the next report has to be readable in one query,
                // and "in progress" alone would not say which flow the user lost.
                + "tutorialBeat=\(tutorialBeat?.rawValue ?? "none") "
                // The clause that decides the case with no unfinished run behind it, and therefore
                // the one the next report will turn on. Reported next to the old fields precisely so
                // "the app vanished when I gave it a permission" is one query away from an answer.
                + "grantJustArrived=\(grantJustArrived) "
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
