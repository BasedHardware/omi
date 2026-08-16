import AppKit
import XCTest

@testable import ContextApp

/// The timeline gesture's rules, asserted directly, because there is no keyboard in a test process.
///
/// Everything here is a case a user hits in their first minute: ⌘C, ⌘Tab, resting a thumb on ⌘ while
/// reading menu hints, then reaching for the other one. The gesture is *both physical Command keys
/// at once*, and the only thing in a `flagsChanged` that can tell those two keys apart is the key
/// code — 55 on the left, 54 on the right — so the samples below are that key code plus the modifier
/// state the event carries after the move.
final class BothCommandKeysTests: XCTestCase {
    private var detector = BothCommandKeys()

    private let left = BothCommandKeys.leftCommand
    private let right = BothCommandKeys.rightCommand

    override func setUp() {
        super.setUp()
        detector = BothCommandKeys()
    }

    /// One `flagsChanged`: the modifier key that moved, and the state afterwards.
    @discardableResult
    private func moved(_ keyCode: UInt16, _ modifiers: ShortcutModifiers, at: TimeInterval) -> Bool {
        detector.flagsChanged(.init(modifiers: modifiers, keyCode: keyCode, at: at))
    }

    func testTheTwoCommandKeysGoingDownTogetherFire() {
        XCTAssertFalse(moved(left, [.command], at: 1.00))
        XCTAssertTrue(moved(right, [.command], at: 1.04))
    }

    /// A hand does not land on two keys at the same instant, and the second key's `flagsChanged`
    /// carries the same `.command` mask as the first — the key code is the whole difference.
    func testEitherKeyMayGoFirst() {
        XCTAssertFalse(moved(right, [.command], at: 1.00))
        XCTAssertTrue(moved(left, [.command], at: 1.03))
    }

    func testPressesExactlyAtTheEdgeOfTheWindowStillCount() {
        XCTAssertFalse(moved(left, [.command], at: 1.00))
        XCTAssertTrue(moved(right, [.command], at: 1.00 + BothCommandKeys.maxOffset))
    }

    /// Holding ⌘ is how macOS shows menu shortcut hints, and a hand resting there for a second before
    /// the other one arrives is not the gesture. This is also what makes the key-code approach safe:
    /// a belief about a key that went stale during a monitoring gap carries a stale timestamp, so it
    /// can never pair with a key going down now.
    func testACommandAlreadyHeldCannotPairWithTheOtherOneLater() {
        XCTAssertFalse(moved(left, [.command], at: 1.00))
        XCTAssertFalse(moved(right, [.command], at: 1.00 + BothCommandKeys.maxOffset + 0.01))
        // Nor eight seconds later, with the right key lifted and pressed again while the left one
        // never moves. This is the drift case: a belief about the left key that outlived the gesture
        // it belonged to can never make a new gesture on its own.
        XCTAssertFalse(moved(right, [.command], at: 9.00))
        XCTAssertFalse(moved(right, [.command], at: 9.02))
    }

    func testOneCommandOnItsOwnNeverFires() {
        XCTAssertFalse(moved(left, [.command], at: 1.00))
        XCTAssertFalse(moved(left, [], at: 3.00))
    }

    /// It fires on the second press, so the keys are still down when the window opens. Nothing may
    /// happen again until they are both up — otherwise a rested hand reopens the timeline.
    func testItDoesNotFireAgainWhileTheKeysStayDown() {
        XCTAssertFalse(moved(left, [.command], at: 1.00))
        XCTAssertTrue(moved(right, [.command], at: 1.04))
        // The right key lifts and comes back while the left never does, so the `.command` bit never
        // clears and nothing has re-armed.
        XCTAssertFalse(moved(right, [.command], at: 1.20))
        XCTAssertFalse(moved(right, [.command], at: 1.23))
    }

    func testReleasingBothKeysRearmsTheGesture() {
        XCTAssertFalse(moved(left, [.command], at: 1.00))
        XCTAssertTrue(moved(right, [.command], at: 1.03))
        XCTAssertFalse(moved(right, [.command], at: 1.30))  // right up, left still holds the bit
        XCTAssertFalse(moved(left, [], at: 1.32))  // and now every Command is up
        XCTAssertFalse(moved(left, [.command], at: 2.00))
        XCTAssertTrue(moved(right, [.command], at: 2.02))
    }

    /// The gesture this one replaced. `⌘⌘` is one key down, up, down, up — the mask says `.command`
    /// twice and the key code is the same both times, so there is never a moment with two keys down.
    func testADoubleTapOfOneCommandKeyNeverFires() {
        XCTAssertFalse(moved(left, [.command], at: 1.00))
        XCTAssertFalse(moved(left, [], at: 1.05))
        XCTAssertFalse(moved(left, [.command], at: 1.15))
        XCTAssertFalse(moved(left, [], at: 1.20))
    }

    /// ⌘C twice quickly is two Command presses in the window. The key struck in between is the only
    /// thing that tells it apart from a gesture, so it had better be enough.
    func testTypingACommandShortcutTwiceNeverFires() {
        XCTAssertFalse(moved(left, [.command], at: 1.00))
        detector.keyPressed()  // C
        XCTAssertFalse(moved(left, [], at: 1.05))
        XCTAssertFalse(moved(left, [.command], at: 1.15))
        detector.keyPressed()  // C again
        XCTAssertFalse(moved(left, [], at: 1.20))
    }

    /// ⌘Tab held with one thumb on each Command key: the keys are both down and inside the window,
    /// and it is still a ⌘-key shortcut rather than this gesture.
    func testAKeyStruckBetweenTheTwoCommandsDisqualifiesTheGesture() {
        XCTAssertFalse(moved(left, [.command], at: 1.00))
        detector.keyPressed()  // Tab
        XCTAssertFalse(moved(right, [.command], at: 1.03))
    }

    /// The regression the sticky flag introduced: an ordinary keystroke arrives with no modifier down
    /// at all, and the modifier release that would have cleared it has already happened. Without the
    /// re-arm on the first Command of a fresh gesture, one keystroke would kill the shortcut until
    /// the next time a modifier happened to go up.
    func testAnEarlierKeystrokeDoesNotPoisonTheNextGesture() {
        detector.keyPressed()  // any letter, no modifiers involved
        XCTAssertFalse(moved(left, [.command], at: 1.00))
        XCTAssertTrue(moved(right, [.command], at: 1.03))
    }

    /// `.bothCommandKeys` carries no held set, so — consistently with `doubleTap`'s `alsoHeld`, where
    /// the held modifiers have to match the chord exactly — the only set it answers to is the empty
    /// one. ⇧ + both Commands is a gesture nothing in this app has claimed.
    func testAnotherModifierHeldMakesItADifferentGesture() {
        XCTAssertFalse(moved(56, [.shift], at: 0.90))  // Shift
        XCTAssertFalse(moved(left, [.command, .shift], at: 1.00))
        XCTAssertFalse(moved(right, [.command, .shift], at: 1.03))
    }

    /// And a modifier arriving mid-gesture disqualifies it for good, rather than the gesture being
    /// restored by the same modifier leaving again.
    func testAModifierArrivingMidGestureDisqualifiesIt() {
        XCTAssertFalse(moved(left, [.command], at: 1.00))
        XCTAssertFalse(moved(56, [.command, .shift], at: 1.02))  // Shift down
        XCTAssertFalse(moved(right, [.command, .shift], at: 1.04))
        XCTAssertFalse(moved(56, [.command], at: 1.06))  // Shift up, both Commands still down
    }

    /// Caps Lock and Fn arrive as `flagsChanged` for reasons that have nothing to do with the keys
    /// being pressed, and `ShortcutModifiers` drops both. Neither may interrupt the gesture.
    func testCapsLockDoesNotDisturbTheGesture() {
        func moved(_ flags: NSEvent.ModifierFlags, _ keyCode: UInt16, _ at: TimeInterval) -> Bool {
            detector.flagsChanged(.init(modifiers: ShortcutModifiers(flags), keyCode: keyCode, at: at))
        }
        XCTAssertFalse(moved([.command, .capsLock], left, 1.00))
        XCTAssertFalse(moved([.command, .capsLock], 57, 1.02))  // Caps Lock itself
        XCTAssertTrue(moved([.command, .capsLock], right, 1.04))
    }

    /// Some third-party keyboards report both Command keys under one key code, and a remapper can do
    /// the same. The toggle then reads the second press as the first key coming up, and the gesture
    /// simply never fires — which is the honest outcome. A detector that guessed would open a window
    /// on one ⌘, on a machine where the user cannot even make the gesture.
    func testAKeyboardThatReportsBothCommandsAsOneKeyNeverFires() {
        XCTAssertFalse(moved(left, [.command], at: 1.00))
        XCTAssertFalse(moved(left, [.command], at: 1.03))
        XCTAssertFalse(moved(left, [.command], at: 1.06))
    }

    /// `reset()` exists because both keys may go up while monitoring is off; a stale belief would
    /// otherwise make the *next* single press look like the second half of a gesture.
    func testResetForgetsAKeyItBelievedWasDown() {
        XCTAssertFalse(moved(left, [.command], at: 1.00))
        detector.reset()
        XCTAssertFalse(moved(right, [.command], at: 1.03))
    }
}

// MARK: - Asking for the grant the gesture needs

/// **The reported bug: pressing both Command keys did nothing.**
///
/// *"When I am pressing both command keys together it is not opening my timeline."* Measured on the
/// reporting Mac: `capture-state.json` had `accessibility: granted false`, so `reapply()` declined to
/// install the `flagsChanged` monitors and the gesture could not fire. Everything about that was
/// already *reported* correctly — `readiness(for:)` answered `.needsAccessibility` and the Settings
/// row said so — and none of it was *actionable*: the app never asked, and an app that has never
/// asked is not listed in Privacy & Security ▸ Accessibility at all, so the button offering to open
/// that pane sent people to a list their app was not in.
///
/// `AXIsProcessTrustedWithOptions` is what both registers the app in that list and raises the alert
/// with a button leading to it, and `reapply()` now calls it. These assert the bounds on doing so,
/// because an alert nobody asked for is its own defect.
final class AccessibilityAskTests: XCTestCase {

    /// Once per launch. `reapply()` runs on every `didBecomeActive`, and this app is activated
    /// constantly — a second alert on every return from another window would be unusable.
    func testTheAlertIsRaisedAtMostOncePerLaunch() {
        XCTAssertTrue(GlobalShortcuts.shouldAsk(alreadyAsked: false, hasFinishedOnboarding: true))
        XCTAssertFalse(GlobalShortcuts.shouldAsk(alreadyAsked: true, hasFinishedOnboarding: true))
    }

    /// Never during onboarding. The first-run flow owns the permission choreography and asks for
    /// Accessibility itself; a second alert racing it at launch would be two dialogs about one
    /// switch, with the app's own card underneath them.
    func testNothingIsAskedBeforeOnboardingHasFinished() {
        XCTAssertFalse(GlobalShortcuts.shouldAsk(alreadyAsked: false, hasFinishedOnboarding: false))
    }

    /// **Per launch and not per install, deliberately** — and this is **A STATIC CHECKER**, not
    /// behavioural coverage. It reads the implementation's source text; it does not run it.
    ///
    /// The claim: macOS drops the grant when the app's signature changes, which is every Sparkle
    /// update — the same way this Mac lost Screen Recording and system audio. A flag persisted once
    /// and kept forever would leave the shortcut dead after an update with nothing said about it.
    ///
    /// Why it is a grep and not an assertion: `hasAskedForAccessibility` is private process state
    /// with no persistence to observe, so there is nothing a second `GlobalShortcuts` could be
    /// handed that would reveal a `UserDefaults` write of it. What this catches is somebody adding
    /// one. It is skipped rather than failed when the source is not beside the test — a packaged or
    /// copied test bundle is not evidence of anything either way — because a checker that reddens on
    /// its own file layout teaches people to ignore it.
    func testTheAskIsNotPersistedAcrossLaunches() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Sources/ContextApp/Shortcuts/GlobalShortcuts.swift")
        guard let source = try? String(contentsOf: url, encoding: .utf8) else {
            throw XCTSkip(
                """
                GlobalShortcuts.swift is not at \(url.path), so this static checker read nothing.

                NOT VERIFIED BY THIS RUN: that the Accessibility ask is not persisted to UserDefaults.
                """)
        }
        XCTAssertFalse(
            source.contains("askedForAccessibility\""),
            "a persisted flag would silence the ask forever, including after an update drops the grant")
    }
}

// MARK: - Chords

final class ShortcutChordTests: XCTestCase {
    /// **One action, one default.** There were two, and `openSearch` — a `⌘⌘⇧` double tap — reached
    /// the same window through the same `window.press()`, so this asserts the count as well as the
    /// chord: a second action reappearing is a second recorder in Settings and a second way to open
    /// one window.
    func testThereIsOneShortcutAndItIsTheBothCommandGesture() {
        XCTAssertEqual(GlobalShortcuts.Action.allCases, [.openActivity])
        XCTAssertEqual(ShortcutAction.allCases, [.openActivity])
        XCTAssertEqual(GlobalShortcuts.Action.openActivity.defaultChord, .bothCommandKeys)
        XCTAssertEqual(GlobalShortcuts.Action.openActivity.defaultChord.display, "⌘ + ⌘")
    }

    /// The gesture may never be printed as `⌘⌘`. That spelling means "tapped twice" wherever this
    /// app reports another tool's binding — Claude's Quick Entry, Codex's `doubleCommand` — so
    /// printing the launch gesture that way would tell the user the wrong thing about their own
    /// keyboard.
    func testTheGestureIsNotSpelledLikeADoubleTap() {
        XCTAssertNotEqual(GlobalShortcuts.Action.openActivity.defaultChord.display, "⌘⌘")
        XCTAssertEqual(ShortcutChord.doubleTap(.command, alsoHeld: []).display, "⌘⌘")
    }

    /// Settings and the shortcut layer describe the same shortcut through two different chord types.
    /// A gesture the recorder spells differently from the thing that fires reads as a second
    /// shortcut nobody bound.
    func testSettingsAndTheShortcutLayerSpellTheDefaultIdentically() {
        XCTAssertEqual(
            ShortcutAction.openActivity.defaultChord.displayString,
            GlobalShortcuts.Action.openActivity.defaultChord.display)
    }

    /// Glyphs are exactly what fails for a gesture nobody has seen before: `⌘ + ⌘` does not say that
    /// the two keys go down together, and read aloud it says even less. Onboarding and any
    /// accessibility label take the words from here rather than inventing their own.
    func testTheGestureHasWordsAsWellAsGlyphs() {
        XCTAssertEqual(ShortcutChord.bothCommandKeys.spokenDescription, "both Command keys")
        XCTAssertEqual(ShortcutAction.openActivity.defaultChord.spokenDescription, "both Command keys")
        XCTAssertEqual(
            ShortcutChord.doubleTap(.command, alsoHeld: []).spokenDescription, "a double tap of ⌘")
        XCTAssertEqual(
            ShortcutChord.doubleTap(.command, alsoHeld: [.shift]).spokenDescription,
            "a double tap of ⌘ with ⇧ held")
        // A key equivalent has no gesture to explain; its glyphs already say it.
        XCTAssertEqual(ShortcutChord.key(label: "K", modifiers: [.command]).spokenDescription, "⌘K")
    }

    /// Apple's modifier order, because a shortcut printed in any other order does not match the menus
    /// it sits beside.
    func testKeyEquivalentsPrintInTheSystemModifierOrder() {
        XCTAssertEqual(
            ShortcutChord.key(label: "K", modifiers: [.command, .shift, .option, .control]).display,
            "⌃⌥⇧⌘K")
    }

    func testTheSubtitleNamesTheDefaultItFallsBackTo() {
        XCTAssertEqual(
            GlobalShortcuts.Action.openActivity.subtitle,
            "Record a keyboard shortcut. Clear it to use ⌘ + ⌘.")
    }

    /// **A row is named for the window it opens.** `⌘ + ⌘` used to open the timeline and the row said
    /// so; it opens Activity now, and a recorder still offering to rebind "Open Timeline Shortcut"
    /// would send anyone who used it to the wrong window — a rename that stopped at the case name is
    /// exactly the kind of half-done that leaves the copy lying.
    func testTheRowsAreNamedForTheWindowsTheyOpen() {
        XCTAssertEqual(GlobalShortcuts.Action.openActivity.title, "Open Activity Shortcut")
        XCTAssertEqual(ShortcutAction.openActivity.title, "Open Activity Shortcut")
        // The two layers print one title for one shortcut, the way they already print one chord.
        for action in ShortcutAction.allCases {
            XCTAssertFalse(
                action.title.contains("Timeline"),
                "\(action.title) names a window this chord no longer opens")
        }
    }
}

// MARK: - Bindings

final class ShortcutStoreTests: XCTestCase {
    private var suite: UserDefaults!
    private var store: GlobalShortcuts.Store!

    override func setUp() {
        super.setUp()
        let name = "context.tests.shortcuts.\(UUID().uuidString)"
        suite = UserDefaults(suiteName: name)
        store = GlobalShortcuts.Store(defaults: suite)
    }

    override func tearDown() {
        for action in GlobalShortcuts.Action.allCases {
            suite.removeObject(forKey: action.storageKey)
        }
        super.tearDown()
    }

    func testNothingStoredMeansTheGestureDefault() {
        for action in GlobalShortcuts.Action.allCases {
            XCTAssertEqual(store.binding(for: action), .gestureDefault)
            XCTAssertEqual(store.chord(for: action), action.defaultChord)
        }
    }

    func testARecordedShortcutRoundTrips() {
        let recorded = GlobalShortcuts.Recorded(keyCode: 40, modifiers: [.command, .shift], label: "K")
        store.setRecorded(recorded, for: .openActivity)
        XCTAssertEqual(store.binding(for: .openActivity), .recorded(recorded))
        XCTAssertEqual(store.chord(for: .openActivity).display, "⇧⌘K")
    }

    /// The behaviour the reference's copy promises out loud.
    func testClearingARecordedShortcutFallsBackToTheGestureDefault() {
        store.setRecorded(
            GlobalShortcuts.Recorded(keyCode: 40, modifiers: [.command], label: "K"), for: .openActivity)
        XCTAssertNotEqual(store.binding(for: .openActivity), .gestureDefault)
        store.setRecorded(nil, for: .openActivity)
        XCTAssertEqual(store.binding(for: .openActivity), .gestureDefault)
        XCTAssertEqual(store.chord(for: .openActivity).display, "⌘ + ⌘")
    }

    /// The keys are namespaced the way every other persisted value in this app is — **and
    /// `openActivity` is filed under the name it shipped with.**
    ///
    /// The literals are the point of this test and they are not tidied. `openActivity` was
    /// `openActivity`, and a stored binding lives at `context.shortcut.<name>.keyEquivalent`; if this
    /// key ever follows the case name, every chord anybody has recorded is orphaned at the old key
    /// and silently replaced by the default. Writing the key out by hand is what makes that a failing
    /// test rather than a rename nobody notices.
    func testStorageKeysFollowTheContextNamespace() {
        XCTAssertEqual(
            GlobalShortcuts.Action.openActivity.storageKey, "context.shortcut.openTimeline.keyEquivalent")
    }

    /// **A chord recorded before the rename still fires after it.**
    ///
    /// The regression the rename could cause and the only one that is invisible without a test: a
    /// user who bound ⌥⌘K to the timeline chord has a dictionary sitting at
    /// `context.shortcut.openTimeline.keyEquivalent`, written by a build that had never heard of
    /// `openActivity`. Nothing announces it going missing — `binding(for:)` simply falls through to
    /// `.gestureDefault`, the machine goes back to answering ⌘ + ⌘, and the user's own shortcut is
    /// gone with no error and no message.
    ///
    /// So the defaults are written here the way the *old build* wrote them — the literal key, and the
    /// three raw fields — rather than through `setRecorded`, which would only prove the store agrees
    /// with itself.
    func testAChordBoundBeforeTheRenameStillResolves() {
        suite.set(
            ["keyCode": 40, "modifiers": ShortcutModifiers([.command, .option]).rawValue, "label": "K"],
            forKey: "context.shortcut.openTimeline.keyEquivalent")

        XCTAssertEqual(
            store.binding(for: .openActivity),
            .recorded(
                GlobalShortcuts.Recorded(keyCode: 40, modifiers: [.command, .option], label: "K")),
            "a binding recorded before the rename was dropped on the floor")
        XCTAssertEqual(store.chord(for: .openActivity).display, "⌥⌘K")
    }
}

// MARK: - Recording

final class ShortcutRecordingTests: XCTestCase {
    private func keyDown(
        _ characters: String, _ keyCode: UInt16, _ modifiers: NSEvent.ModifierFlags
    ) -> NSEvent {
        NSEvent.keyEvent(
            with: .keyDown,
            location: .zero,
            modifierFlags: modifiers,
            timestamp: 0,
            windowNumber: 0,
            context: nil,
            characters: characters,
            charactersIgnoringModifiers: characters,
            isARepeat: false,
            keyCode: keyCode)!
    }

    func testARecordedShortcutTakesItsLabelFromTheEvent() {
        let recorded = GlobalShortcuts.Recorded.from(keyDown("k", 40, [.command, .option]))
        XCTAssertEqual(recorded?.label, "K")
        XCTAssertEqual(recorded?.modifiers, [.command, .option])
        XCTAssertEqual(recorded?.chord.display, "⌥⌘K")
    }

    /// A bare key as a system-wide shortcut would eat that letter in every app on the machine, and
    /// ⇧ alone does not change that.
    func testABareKeyIsRefused() {
        XCTAssertNil(GlobalShortcuts.Recorded.from(keyDown("k", 40, [])))
        XCTAssertNil(GlobalShortcuts.Recorded.from(keyDown("K", 40, [.shift])))
    }

    func testEscapeAndReturnAreRefused() {
        XCTAssertNil(GlobalShortcuts.Recorded.from(keyDown("\u{1b}", 53, [.command])))
        XCTAssertNil(GlobalShortcuts.Recorded.from(keyDown("\r", 36, [.command, .option])))
    }

    /// Space prints a space, which is unreadable in a recorder.
    func testKeysThatPrintNothingLegibleGetAName() {
        XCTAssertEqual(GlobalShortcuts.Recorded.from(keyDown(" ", 49, [.control]))?.label, "Space")
        XCTAssertEqual(GlobalShortcuts.Recorded.from(keyDown("\u{f702}", 123, [.option]))?.label, "←")
    }
}

// MARK: - Conflicts

/// Real files on disk, because the whole point of this surface is that it never claims anything it did
/// not read.
final class ShortcutConflictsTests: XCTestCase {
    private var root: URL!

    override func setUpWithError() throws {
        try super.setUpWithError()
        // Symlinks resolved up front (`/var` is really `/private/var`), because the scan reports the
        // standardized path and the assertions compare against it.
        root = URL(fileURLWithPath: NSTemporaryDirectory())
            .resolvingSymlinksInPath()
            .appendingPathComponent("context-conflicts-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: root)
        try super.tearDownWithError()
    }

    // MARK: Fixtures

    private func path(_ name: String) -> String { root.appendingPathComponent(name).path }

    private func write(_ contents: String, to name: String) throws {
        try contents.write(to: root.appendingPathComponent(name), atomically: true, encoding: .utf8)
    }

    private func makeDirectory(_ name: String) throws {
        try FileManager.default.createDirectory(
            at: root.appendingPathComponent(name, isDirectory: true), withIntermediateDirectories: true)
    }

    /// Nothing exists unless a test puts it there, so an assertion can never be satisfied by whatever
    /// happens to be installed on the machine running the suite.
    private func locations(
        claudeInstalled: Bool = false, codexInstalled: Bool = false, cursorInstalled: Bool = false
    ) throws -> ShortcutConflicts.Locations {
        if claudeInstalled { try makeDirectory("Claude.app") }
        if codexInstalled { try makeDirectory("Codex.app") }
        if cursorInstalled { try makeDirectory("Cursor.app") }
        return ShortcutConflicts.Locations(
            claudeApp: path("Claude.app"),
            claudeConfig: path("claude-config.json"),
            codexApp: path("Codex.app"),
            codexKeymap: path("keybindings.json"),
            codexGlobalState: path("codex-global-state.json"),
            cursorApp: path("Cursor.app"),
            cursorMainScript: path("cursor-main.js"))
    }

    private static let ourDefaults: [GlobalShortcuts.Action: ShortcutChord] = [
        .openActivity: .bothCommandKeys
    ]

    // MARK: Nothing installed

    func testNothingInstalledMeansNoFindingsAndNoRow() throws {
        let report = ShortcutConflicts.scan(ours: Self.ourDefaults, at: try locations(), airgapMode: false)
        XCTAssertEqual(report.findings[.claudeDesktop], ShortcutConflicts.Finding.notInstalled)
        XCTAssertEqual(report.findings[.codex], ShortcutConflicts.Finding.notInstalled)
        XCTAssertEqual(report.findings[.cursor], ShortcutConflicts.Finding.notInstalled)
        XCTAssertTrue(report.conflicts.isEmpty)
    }

    // MARK: Codex

    /// The reference's exact row, and the only shape that earns it: Codex's own keymap file, naming
    /// one of its three system-wide commands, bound to a double tap of Command.
    ///
    /// The chord it collides with is passed in rather than taken from our defaults, because it is no
    /// longer one of them — see the test below.
    func testCodexBindingDoubleCommandInItsKeymapIsARealConflict() throws {
        try write(#"[{"command":"globalDictationToggle","key":"doubleCommand"}]"#, to: "keybindings.json")
        let report = ShortcutConflicts.scan(
            ours: [.openActivity: .doubleTap(.command, alsoHeld: [])],
            at: try locations(codexInstalled: true), airgapMode: false)

        guard case .bound(_, let binding, let evidence)? = report.findings[.codex] else {
            return XCTFail("expected a bound finding, got \(String(describing: report.findings[.codex]))")
        }
        XCTAssertEqual(binding.display, "⌘⌘")
        XCTAssertEqual(evidence, .configFile(path: path("keybindings.json")))

        XCTAssertEqual(report.conflicts.count, 1)
        let conflict = report.conflicts[0]
        XCTAssertEqual(conflict.action, .openActivity)
        XCTAssertEqual(conflict.title, "Codex also uses ⌘⌘")
        XCTAssertTrue(conflict.subtitle.contains("keybindings.json"), conflict.subtitle)
        // The remedy is instructions plus the file, never an edit we make.
        XCTAssertEqual(conflict.remedy.revealPath, path("keybindings.json"))
    }

    /// …and against the defaults this app actually ships, the same Codex keymap is no longer in the
    /// way of anything.
    ///
    /// Both keys going down puts the `.command` bit down **once**, so a tool watching for two taps of
    /// it never sees the timeline's gesture. The binding is still read and still reported — the claim
    /// is about a collision, not about whether Codex bound something — and no row is drawn.
    func testCodexsDoubleCommandNoLongerCollidesNowTheTimelineIsBothCommandKeys() throws {
        try write(#"[{"command":"globalDictationToggle","key":"doubleCommand"}]"#, to: "keybindings.json")
        let report = ShortcutConflicts.scan(
            ours: Self.ourDefaults, at: try locations(codexInstalled: true), airgapMode: false)

        guard case .bound(_, let binding, _)? = report.findings[.codex] else {
            return XCTFail("expected a bound finding, got \(String(describing: report.findings[.codex]))")
        }
        XCTAssertEqual(binding.display, "⌘⌘")
        XCTAssertTrue(report.conflicts.isEmpty, "⌘⌘ and ⌘ + ⌘ are different gestures")
    }

    /// A stock Codex. Its three global commands ship with no default binding, so there is nothing to
    /// warn about — which is exactly why the row has to be conditional.
    func testAStockCodexBindsNothingSystemWide() throws {
        let report = ShortcutConflicts.scan(
            ours: Self.ourDefaults, at: try locations(codexInstalled: true), airgapMode: false)
        guard case .noGlobalBinding(let reason)? = report.findings[.codex] else {
            return XCTFail("expected no global binding, got \(String(describing: report.findings[.codex]))")
        }
        XCTAssertTrue(reason.contains("no keybindings.json"), reason)
        XCTAssertTrue(report.conflicts.isEmpty)
    }

    /// A keymap full of window shortcuts is not a global binding. Treating ⌘W as a system-wide chord
    /// would put a false row in front of the user on nearly every machine.
    func testCodexWindowShortcutsAreNotGlobalBindings() throws {
        try write(#"[{"command":"closeTab","key":"CmdOrCtrl+W"}]"#, to: "keybindings.json")
        let report = ShortcutConflicts.scan(
            ours: Self.ourDefaults, at: try locations(codexInstalled: true), airgapMode: false)
        guard case .noGlobalBinding? = report.findings[.codex] else {
            return XCTFail("expected no global binding, got \(String(describing: report.findings[.codex]))")
        }
        XCTAssertTrue(report.conflicts.isEmpty)
    }

    /// A single bare ⌘ fires on the first ⌘ of our gesture, so it collides even though the two
    /// bindings are not the same chord. Comparing chords alone would miss this.
    ///
    /// It used to produce **two** rows, one per default, because `openSearch`'s `⌘⌘⇧` started on
    /// Command too. One action, one row — and one row is also the honest count: two rows over one
    /// window told the user they had two problems.
    func testASingleBareCommandCollidesWithTheCommandGesture() throws {
        try write(#"[{"command":"globalDictationHold","key":"leftCommand"}]"#, to: "keybindings.json")
        let report = ShortcutConflicts.scan(
            ours: Self.ourDefaults, at: try locations(codexInstalled: true), airgapMode: false)
        XCTAssertEqual(report.conflicts.count, 1, "one row, because there is one shortcut")
        XCTAssertEqual(report.conflicts.first?.tool, .codex)
        XCTAssertEqual(
            report.conflicts.first(where: { $0.action == .openActivity })?.title, "Codex also uses ⌘ + ⌘")
    }

    /// The legacy home of the popout window's chord, still read because a Codex configured before the
    /// keymap existed has its value only here.
    func testCodexLegacyGlobalStateIsStillRead() throws {
        try write(#"{"hotkeyWindowHotkey":"doubleCommand"}"#, to: "codex-global-state.json")
        let report = ShortcutConflicts.scan(
            // A double tap is what that legacy value means, so a double tap is what it can be in the
            // way of — our own defaults have moved off that chord, which the test above pins down.
            ours: [.openActivity: .doubleTap(.command, alsoHeld: [])],
            at: try locations(codexInstalled: true), airgapMode: false)
        XCTAssertEqual(report.conflicts.count, 1)
        XCTAssertEqual(report.conflicts[0].evidence, .configFile(path: path("codex-global-state.json")))
    }

    /// The guard against fabrication: an unreadable config produces no claim at all.
    func testAMalformedKeymapReportsUndeterminedAndShowsNothing() throws {
        try write("{ not json", to: "keybindings.json")
        let report = ShortcutConflicts.scan(
            ours: Self.ourDefaults, at: try locations(codexInstalled: true), airgapMode: false)
        guard case .undetermined? = report.findings[.codex] else {
            return XCTFail("expected undetermined, got \(String(describing: report.findings[.codex]))")
        }
        XCTAssertTrue(report.conflicts.isEmpty)
    }

    // MARK: Claude

    /// Claude only writes `quickEntryShortcut` once the user changes it, so on a stock install the
    /// shipped default applies — a double tap of Option. Against our own defaults that is no conflict,
    /// which is the case that matters: it is why our ⌘⌘ can ship at all.
    func testClaudeOnItsDefaultDoesNotConflictWithOurDefaults() throws {
        try write(#"{"menuBarEnabled":true}"#, to: "claude-config.json")
        let report = ShortcutConflicts.scan(
            ours: Self.ourDefaults, at: try locations(claudeInstalled: true), airgapMode: false)
        guard case .bound(_, let binding, let evidence)? = report.findings[.claudeDesktop] else {
            return XCTFail("expected a bound finding, got \(String(describing: report.findings[.claudeDesktop]))")
        }
        XCTAssertEqual(binding.display, "⌥⌥")
        guard case .shippedDefault = evidence else { return XCTFail("expected a shipped-default claim") }
        XCTAssertTrue(report.conflicts.isEmpty)
    }

    /// …and if the user rebinds *ours* to ⌥⌥, that same default is now in the way, and the row says so
    /// while being explicit that it rests on a default rather than on their config.
    func testRebindingOurselvesOntoClaudesDefaultIsReported() throws {
        try write(#"{"menuBarEnabled":true}"#, to: "claude-config.json")
        let report = ShortcutConflicts.scan(
            ours: [.openActivity: .doubleTap(.option, alsoHeld: [])],
            at: try locations(claudeInstalled: true), airgapMode: false)
        XCTAssertEqual(report.conflicts.count, 1)
        XCTAssertEqual(report.conflicts[0].title, "Claude also uses ⌥⌥")
        XCTAssertTrue(report.conflicts[0].subtitle.contains("shipped default"), report.conflicts[0].subtitle)
    }

    func testClaudeQuickEntryTurnedOffIsNotAConflict() throws {
        try write(#"{"quickEntryShortcut":"off"}"#, to: "claude-config.json")
        let report = ShortcutConflicts.scan(
            ours: [.openActivity: .doubleTap(.option, alsoHeld: [])],
            at: try locations(claudeInstalled: true), airgapMode: false)
        guard case .noGlobalBinding? = report.findings[.claudeDesktop] else {
            return XCTFail("expected no global binding, got \(String(describing: report.findings[.claudeDesktop]))")
        }
        XCTAssertTrue(report.conflicts.isEmpty)
    }

    /// A recorded key equivalent on both sides, compared on the printed key rather than a key code —
    /// which is the only thing an accelerator string and an `NSEvent` both carry.
    func testAnAcceleratorInClaudesConfigMatchesOurRecordedShortcut() throws {
        try write(#"{"quickEntryShortcut":{"accelerator":"CmdOrCtrl+Shift+K"}}"#, to: "claude-config.json")
        let report = ShortcutConflicts.scan(
            ours: [.openActivity: .key(label: "K", modifiers: [.command, .shift])],
            at: try locations(claudeInstalled: true), airgapMode: false)
        XCTAssertEqual(report.conflicts.count, 1)
        XCTAssertEqual(report.conflicts[0].chord.display, "⇧⌘K")
        XCTAssertEqual(report.conflicts[0].evidence, .configFile(path: path("claude-config.json")))
    }

    func testCapsLockQuickEntryCannotCollide() throws {
        try write(#"{"quickEntryShortcut":"double-tap-capslock"}"#, to: "claude-config.json")
        let report = ShortcutConflicts.scan(
            ours: Self.ourDefaults, at: try locations(claudeInstalled: true), airgapMode: false)
        XCTAssertTrue(report.conflicts.isEmpty)
    }

    // MARK: Cursor

    /// Cursor's shortcuts are window-scoped, and that is *checked* rather than assumed: an Electron
    /// app reaches an OS-global chord through `globalShortcut`, so its absence from the main process
    /// is the evidence.
    func testCursorWithNoGlobalShortcutApiIsWindowScoped() throws {
        try write("// no global shortcuts here\nconsole.log('hi')\n", to: "cursor-main.js")
        let report = ShortcutConflicts.scan(
            ours: Self.ourDefaults, at: try locations(cursorInstalled: true), airgapMode: false)
        guard case .noGlobalBinding(let reason)? = report.findings[.cursor] else {
            return XCTFail("expected no global binding, got \(String(describing: report.findings[.cursor]))")
        }
        XCTAssertTrue(reason.contains("only fire while Cursor is focused"), reason)
    }

    /// And if a future Cursor does register one, the honest answer is "I can't tell" — not silence
    /// dressed up as safety, and not a fabricated row either.
    func testCursorThatRegistersGlobalShortcutsIsUndetermined() throws {
        try write("app.whenReady().then(() => globalShortcut.register('Cmd+K', run))\n", to: "cursor-main.js")
        let report = ShortcutConflicts.scan(
            ours: Self.ourDefaults, at: try locations(cursorInstalled: true), airgapMode: false)
        guard case .undetermined? = report.findings[.cursor] else {
            return XCTFail("expected undetermined, got \(String(describing: report.findings[.cursor]))")
        }
        XCTAssertTrue(report.conflicts.isEmpty)
    }

    // MARK: Airgap

    /// Airgap Mode stops the scan reading anyone's files, even though none of it is a network
    /// request. The row then says it cannot tell, which is the truthful thing for it to say.
    func testAirgapModeStopsTheScanAndReportsThatItCannotTell() throws {
        // A bare ⌘, which is in the way of our gesture — so the fixture really would draw a row,
        // which is the half of this test that makes the other half mean anything.
        try write(#"[{"command":"globalDictationToggle","key":"leftCommand"}]"#, to: "keybindings.json")
        let locations = try locations(claudeInstalled: true, codexInstalled: true, cursorInstalled: true)

        // Off: the conflict is found.
        XCTAssertEqual(
            ShortcutConflicts.scan(ours: Self.ourDefaults, at: locations, airgapMode: false).conflicts.count, 1)

        let airgapped = ShortcutConflicts.scan(ours: Self.ourDefaults, at: locations, airgapMode: true)
        XCTAssertTrue(airgapped.conflicts.isEmpty)
        for tool in ShortcutConflicts.Tool.allCases {
            guard case .undetermined(let reason)? = airgapped.findings[tool] else {
                return XCTFail("expected undetermined for \(tool), got \(String(describing: airgapped.findings[tool]))")
            }
            XCTAssertTrue(reason.contains("Airgap Mode"), reason)
        }
    }

    // MARK: Accelerators

    func testAcceleratorParsing() {
        XCTAssertEqual(ShortcutConflicts.parseAccelerator("CmdOrCtrl+Shift+K")?.display, "⇧⌘K")
        XCTAssertEqual(ShortcutConflicts.parseAccelerator("Alt+Space")?.display, "⌥Space")
        XCTAssertEqual(ShortcutConflicts.parseAccelerator("Control+Option+Left")?.display, "⌃⌥←")
        // A key with no modifier is not something either product can register globally.
        XCTAssertNil(ShortcutConflicts.parseAccelerator("K"))
        // Two non-modifier tokens is not an accelerator we understand, and guessing is not allowed.
        XCTAssertNil(ShortcutConflicts.parseAccelerator("Cmd+K+J"))
    }
}
