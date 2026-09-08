import AppKit
import ContextCore
import XCTest

@testable import ContextApp

// MARK: - A registry that does not take a system-wide hot key

/// `GlobalShortcuts` with the Carbon call replaced by a rule.
///
/// It keeps the same contract the real one has, because the adapter's behaviour hangs off it:
/// `setRecorded` stores *and* re-applies (which is what "the shortcut works without a relaunch"
/// means), a rejected registration leaves the value stored while `readiness` reports the refusal,
/// and `armedChords` only lists what is actually live.
@MainActor
private final class FakeShortcutRegistry: ShortcutRegistry {
    /// Labels this machine "already has taken", i.e. what `RegisterEventHotKey` would refuse.
    var refusedLabels: Set<String> = []
    /// Whether this Mac is AX-trusted. False is the state that used to be invisible in Settings: the
    /// gesture defaults are watched for through a system-wide monitor macOS gates behind
    /// Accessibility, so without it they simply never fire.
    var isAXTrusted = true
    /// Every re-arm. The count is the assertion behind "immediately": a provider that only wrote to
    /// `UserDefaults` would leave this at zero and look identical in Settings.
    private(set) var reapplies = 0

    private var bindings: [GlobalShortcuts.Action: GlobalShortcuts.Binding] = [:]

    func binding(for action: GlobalShortcuts.Action) -> GlobalShortcuts.Binding {
        bindings[action] ?? .gestureDefault
    }

    func setRecorded(_ recorded: GlobalShortcuts.Recorded?, for action: GlobalShortcuts.Action) {
        bindings[action] = recorded.map(GlobalShortcuts.Binding.recorded) ?? .gestureDefault
        reapplies += 1
    }

    func readiness(for action: GlobalShortcuts.Action) -> GlobalShortcuts.Readiness {
        switch binding(for: action) {
        case .gestureDefault:
            // Exactly `GlobalShortcuts.readiness`'s own rule for this case.
            return isAXTrusted ? .armed : .needsAccessibility
        case .recorded(let recorded):
            guard refusedLabels.contains(recorded.label) else { return .armed }
            return .rejected("Something else on this Mac already uses \(recorded.chord.display).")
        }
    }

    func armedChords() -> [GlobalShortcuts.Action: ShortcutChord] {
        var out: [GlobalShortcuts.Action: ShortcutChord] = [:]
        for action in GlobalShortcuts.Action.allCases where readiness(for: action) == .armed {
            switch binding(for: action) {
            case .gestureDefault: out[action] = action.defaultChord
            case .recorded(let recorded): out[action] = recorded.chord
            }
        }
        return out
    }
}

// MARK: - The adapter

/// The seam between the two recorders in Settings and the hot keys that fire.
///
/// Every one of these was a live defect: the pane was bound to an in-memory dictionary, so recording
/// reported success and changed nothing, clearing changed nothing, and the conflict scanner had no
/// caller at all.
@MainActor
final class LiveShortcutBindingsTests: XCTestCase {

    private var registry: FakeShortcutRegistry!

    override func setUp() {
        super.setUp()
        registry = FakeShortcutRegistry()
    }

    /// `⌥⌘K`, on a layout where key 40 prints K.
    private static let optionCommandK = SettingsShortcutChord(
        keyCode: 40, modifierFlags: [.command, .option])

    private func provider(
        scan: @escaping ([GlobalShortcuts.Action: ShortcutChord]) -> ShortcutConflicts.Report = { _ in
            ShortcutConflicts.Report(findings: [:], conflicts: [])
        },
        exclusions: ExclusionEngine = .shared
    ) -> LiveShortcutBindings {
        LiveShortcutBindings(
            registry: registry,
            // Pinned: the live lookup asks whichever keyboard layout the machine running the suite
            // has selected, which is not something a hermetic test may assert against.
            label: { $0 == 40 ? "K" : "Key \($0)" },
            scan: scan,
            exclusions: exclusions)
    }

    /// A throwaway engine on a throwaway configuration file, so flipping Airgap Mode in a test never
    /// touches the developer's own `exclusions.json`.
    private func temporaryExclusions() throws -> ExclusionEngine {
        let root = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("context-shortcut-airgap-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        addTeardownBlock { try? FileManager.default.removeItem(at: root) }
        return ExclusionEngine(
            configurationURL: root.appendingPathComponent("exclusions.json"),
            framesRoot: root.appendingPathComponent("Frames", isDirectory: true))
    }

    // MARK: Nothing recorded

    /// The ✕ on each recorder is offered only when `binding(for:)` is non-nil. A store that reported
    /// the gesture default as a binding put a "clear" button on a virgin install, offering to
    /// clear a slot that was already clear.
    func testAVirginInstallReportsNoRecordedBindingSoThereIsNothingToClear() {
        let bindings = provider()
        for action in ShortcutAction.allCases {
            XCTAssertNil(bindings.binding(for: action), "\(action.title) has never been recorded")
        }
    }

    // MARK: Recording

    func testRecordingPersistsThroughTheStoreAndRearmsImmediately() {
        let bindings = provider()
        XCTAssertEqual(bindings.record(Self.optionCommandK, for: .openActivity), .recorded)

        // Stored where the hot key layer reads it, not in the provider.
        guard case .recorded(let recorded) = registry.binding(for: .openActivity) else {
            return XCTFail("the chord never reached the shortcut layer")
        }
        XCTAssertEqual(recorded.keyCode, 40)
        XCTAssertEqual(recorded.modifiers, [.command, .option])
        // The label is what makes the chord comparable to another tool's `Cmd+Alt+K`, and printable.
        XCTAssertEqual(recorded.label, "K")
        XCTAssertEqual(recorded.chord.display, "⌥⌘K")

        // Re-armed on the way through: no relaunch, no second step.
        XCTAssertEqual(registry.reapplies, 1)
        // And the recorder now shows a recorded chord, so the ✕ appears.
        XCTAssertEqual(bindings.binding(for: .openActivity), Self.optionCommandK)
    }

    /// Caps Lock is in `deviceIndependentFlagsMask`, so the recorder can hand us a chord carrying it.
    /// Storing that would make the same keypress record differently depending on a light on the
    /// keyboard.
    func testCapsLockIsNotPartOfARecordedChord() {
        let bindings = provider()
        let withCapsLock = SettingsShortcutChord(
            keyCode: 40, modifierFlags: [.command, .option, .capsLock])
        XCTAssertEqual(bindings.record(withCapsLock, for: .openActivity), .recorded)
        XCTAssertEqual(bindings.binding(for: .openActivity), Self.optionCommandK)
    }

    func testClearingReturnsToTheGestureDefaultAndRearms() {
        let bindings = provider()
        XCTAssertEqual(bindings.record(Self.optionCommandK, for: .openActivity), .recorded)

        bindings.clear(.openActivity)

        XCTAssertEqual(registry.binding(for: .openActivity), .gestureDefault)
        XCTAssertNil(bindings.binding(for: .openActivity), "cleared is not 'bound to the default'")
        // The clear is a re-arm too: it is what puts the `flagsChanged` monitor back.
        XCTAssertEqual(registry.reapplies, 2)
        XCTAssertEqual(registry.armedChords()[.openActivity], ShortcutChord.bothCommandKeys)
    }

    // MARK: Readiness

    /// **The pane could not ask whether the chord it prints will fire.**
    ///
    /// `GlobalShortcuts.readiness(for:)` exists for Settings — its own note says the gesture defaults
    /// cannot be registered as hot keys, that macOS gates the `flagsChanged` monitor behind
    /// Accessibility, and that "when that grant is missing the shortcut does not fire, and
    /// `readiness(for:)` says so rather than letting Settings imply otherwise". `ShortcutBindingProvider`
    /// had no member for it, so Settings never asked and printed `⌘ + ⌘` on a Mac where pressing it
    /// did nothing whatsoever. This is the seam that closes it.
    func testAGestureDefaultWithoutAccessibilityReportsThatItWillNotFire() {
        let bindings = provider()
        for action in ShortcutAction.allCases {
            XCTAssertEqual(bindings.readiness(for: action), .armed)
        }

        registry.isAXTrusted = false
        for action in ShortcutAction.allCases {
            XCTAssertEqual(
                bindings.readiness(for: action), .needsAccessibility,
                "\(action.title) is on its gesture default, which cannot fire without the grant")
        }
    }

    /// A **recorded** chord goes through `RegisterEventHotKey`, which needs no permission at all —
    /// so it stays armed on the same ungranted Mac. That asymmetry is the whole reason the recorder
    /// is worth offering to a user who refused Accessibility, and a readiness that reported the
    /// permission for both kinds of binding would send them to a pane that cannot help.
    func testARecordedKeyEquivalentStaysArmedWithoutAccessibility() {
        let bindings = provider()
        XCTAssertEqual(bindings.record(Self.optionCommandK, for: .openActivity), .recorded)

        registry.isAXTrusted = false
        XCTAssertEqual(
            bindings.readiness(for: .openActivity), .armed,
            "a recorded key equivalent is a Carbon hot key and needs no grant at all")

        // …and the same slot back on its gesture default is the one that stops working, because a
        // gesture can only be watched for and macOS gates the watching behind Accessibility.
        bindings.clear(.openActivity)
        XCTAssertEqual(bindings.readiness(for: .openActivity), .needsAccessibility)
    }

    /// A refusal carries macOS's own reason all the way to the row. Flattening it into a generic
    /// sentence would drop the only part the user can act on — which chord is already taken.
    func testARefusedRegistrationSurfacesItsReasonAsReadiness() {
        let bindings = provider()
        registry.refusedLabels = ["K"]
        // Recorded straight into the registry, bypassing `record`'s rollback, because the state
        // being asserted is the one a *previously* stored chord lands in when the machine's other
        // software takes the shortcut between launches.
        registry.setRecorded(
            GlobalShortcuts.Recorded(keyCode: 40, modifiers: [.command, .option], label: "K"),
            for: .openActivity)

        guard case .rejected(let reason) = bindings.readiness(for: .openActivity) else {
            return XCTFail("a chord macOS refused must not read as armed")
        }
        XCTAssertTrue(reason.contains("already uses"), reason)
        XCTAssertFalse(bindings.readiness(for: .openActivity).isArmed)
    }

    // MARK: Refusal

    /// The failure the old provider could not express: it returned `.recorded` whatever happened, so
    /// a chord another app already owned looked bound and did nothing.
    func testARefusedRegistrationIsReportedAndLeavesThePreviousShortcutArmed() {
        let bindings = provider()
        registry.refusedLabels = ["K"]

        guard case .rejected(let reason) = bindings.record(Self.optionCommandK, for: .openActivity) else {
            return XCTFail("a chord macOS will not register must not report success")
        }
        XCTAssertTrue(reason.contains("already uses"), reason)

        // Rolled back, so the user is left with a shortcut that works rather than a stored dead one.
        XCTAssertEqual(registry.binding(for: .openActivity), .gestureDefault)
        XCTAssertNil(bindings.binding(for: .openActivity))
        XCTAssertEqual(registry.readiness(for: .openActivity), .armed)
    }

    /// A refusal must restore the *previous recording*, not just wipe the slot.
    func testARefusalAfterAnEarlierRecordingRestoresTheEarlierOne() {
        let bindings = provider()
        XCTAssertEqual(bindings.record(Self.optionCommandK, for: .openActivity), .recorded)

        registry.refusedLabels = ["Key 49"]
        let space = SettingsShortcutChord(keyCode: 49, modifierFlags: [.control])
        guard case .rejected = bindings.record(space, for: .openActivity) else {
            return XCTFail("expected the refusal")
        }
        XCTAssertEqual(bindings.binding(for: .openActivity), Self.optionCommandK)
    }

    // MARK: Validation

    /// Refused before the registry is touched: `RegisterEventHotKey` would happily take ⌘Q and the
    /// user would lose Quit in every app on the machine.
    func testChordsMacOSOwnsAreRefusedWithoutReachingTheRegistry() {
        let bindings = provider()
        for reserved in SettingsShortcutChord.reservedByMacOS {
            guard case .rejected = bindings.record(reserved, for: .openActivity) else {
                return XCTFail("\(reserved.displayString) is reserved by macOS and must be refused")
            }
        }
        // ⇧K is K to the rest of the system, so binding it eats a letter everywhere.
        let shiftOnly = SettingsShortcutChord(keyCode: 40, modifierFlags: [.shift])
        guard case .rejected = bindings.record(shiftOnly, for: .openActivity) else {
            return XCTFail("a shift-only chord must be refused")
        }
        // Return means something specific in every app; the shortcut layer refuses it on the event
        // path too, and the two paths must agree.
        let commandReturn = SettingsShortcutChord(keyCode: 36, modifierFlags: [.command])
        guard case .rejected = bindings.record(commandReturn, for: .openActivity) else {
            return XCTFail("↵ must be refused")
        }
        XCTAssertEqual(registry.reapplies, 0, "a refused chord must never be stored or armed")
    }

    /// The app's own gestures are not recordable, and the guard that says so had no test.
    ///
    /// The recorder cannot send one today — it arms on `keyDown`, and pressing two Command keys
    /// produces none — but the seam accepts a modifier-only chord, and a future recorder watching
    /// `flagsChanged` would produce exactly this. `RegisterEventHotKey` has nothing to take from a
    /// chord with no key, so accepting it would store a shortcut that shows in the row and never
    /// fires. Asking for the gesture is what *clearing* the slot already does.
    func testTheAppsOwnGesturesCannotBeRecorded() {
        let bindings = provider()
        for gesture in [SettingsShortcutChord.Gesture.bothCommandKeys, .doubleTap] {
            let chord = SettingsShortcutChord(modifierFlags: .command, gesture: gesture)
            guard case .rejected = bindings.record(chord, for: .openActivity) else {
                return XCTFail("\(chord.displayString) has no key for a hot key to take")
            }
        }
        XCTAssertEqual(registry.reapplies, 0, "a refused chord must never be stored or armed")
        XCTAssertNil(bindings.binding(for: .openActivity))
    }

    // MARK: Observers

    func testObserversAreNotifiedOnRecordAndClearAndReleased() {
        let bindings = provider()
        var notifications = 0
        let token = bindings.addObserver { notifications += 1 }

        XCTAssertEqual(bindings.record(Self.optionCommandK, for: .openActivity), .recorded)
        bindings.clear(.openActivity)
        XCTAssertEqual(notifications, 2)

        bindings.removeObserver(token)
        bindings.clear(.openActivity)
        XCTAssertEqual(notifications, 2, "a released observer must stop hearing about changes")
    }

    // MARK: Conflicts

    /// The scanner had no caller anywhere in the app, so the Conflicts section could never render.
    /// This drives the real scan over real fixture files, exactly as `ShortcutConflictsTests` does,
    /// and asserts the row the pane would draw from it.
    func testACodexKeymapClaimingABareCommandBecomesARowWithItsEvidence() throws {
        let root = URL(fileURLWithPath: NSTemporaryDirectory())
            .resolvingSymlinksInPath()
            .appendingPathComponent("context-live-conflicts-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(
            at: root.appendingPathComponent("Codex.app", isDirectory: true), withIntermediateDirectories: true
        )
        defer { try? FileManager.default.removeItem(at: root) }

        let keymap = root.appendingPathComponent("keybindings.json")
        // A bare left ⌘, which is what a tool has to bind to be in the way of this app's timeline
        // gesture: it fires on the first of the two keys. A `doubleCommand` binding is not — both
        // keys going down puts the `.command` bit down once, so Codex's double-tap monitor never
        // sees it, and the scan says so rather than drawing a row for a collision that cannot happen.
        try #"[{"command":"hotkeyWindow","key":"leftCommand"}]"#
            .write(to: keymap, atomically: true, encoding: .utf8)
        let locations = ShortcutConflicts.Locations(
            claudeApp: root.appendingPathComponent("Claude.app").path,
            claudeConfig: root.appendingPathComponent("claude-config.json").path,
            codexApp: root.appendingPathComponent("Codex.app").path,
            codexKeymap: keymap.path,
            codexGlobalState: root.appendingPathComponent("codex-global-state.json").path,
            cursorApp: root.appendingPathComponent("Cursor.app").path,
            cursorMainScript: root.appendingPathComponent("cursor-main.js").path)

        let bindings = provider(scan: { ours in
            // Airgap off explicitly: the production default reads it from `ExclusionEngine`, which is
            // the user's real configuration and has no business deciding a test's outcome.
            ShortcutConflicts.scan(ours: ours, at: locations, airgapMode: false)
        })

        let rows = bindings.conflicts()
        XCTAssertEqual(rows.count, 1, "a bare ⌘ starts this app's one gesture")
        let row = try XCTUnwrap(rows.first { $0.action == .openActivity })
        XCTAssertEqual(row.owner, "Codex")
        // Spelled by `SettingsShortcutChord` here and by `ShortcutChord` in the scan: one gesture,
        // one spelling, or the row describes a shortcut the user does not recognise as theirs.
        XCTAssertEqual(row.title, "Codex also uses ⌘ + ⌘")
        // The claim is inspectable: the row names the file it was read out of.
        XCTAssertTrue(row.subtitle.contains("keybindings.json"), row.subtitle)
        // Never "Switch Codex to ⌥⌥" — this app does not rewrite another product's configuration.
        XCTAssertEqual(row.remedyTitle, "Reveal in Finder")
    }

    /// A rebind moves the conflict with it: the scan is asked about the chords that are armed *now*,
    /// so no row survives the shortcut it described. A provider that scanned once and cached would
    /// leave the warning on screen after the user did exactly what it asked.
    func testRecordingOffTheContestedChordRemovesTheRow() {
        // Stands in for a tool that owns ⌘ + ⌘ and nothing else, without touching the filesystem.
        let bindings = provider(scan: { ours in
            let contested = ShortcutChord.bothCommandKeys
            return ShortcutConflicts.Report(
                findings: [:],
                conflicts: ours.filter { $0.value == contested }.map { action, chord in
                    ShortcutConflicts.Conflict(
                        tool: .codex,
                        action: action,
                        chord: chord,
                        feature: "Popout Window",
                        evidence: .shippedDefault(note: "Fixture."),
                        remedy: ShortcutConflicts.Remedy(instruction: "Change it.", revealPath: nil))
                })
        })

        XCTAssertEqual(bindings.conflicts().count, 1, "⌘ + ⌘ is contested while it is the binding")
        // A conflict with nowhere to reveal offers no button rather than a dead one.
        XCTAssertNil(bindings.conflicts().first?.remedyTitle)

        XCTAssertEqual(bindings.record(Self.optionCommandK, for: .openActivity), .recorded)
        XCTAssertTrue(bindings.conflicts().isEmpty, "nothing claims ⌥⌘K")
    }

    /// The pane asks on every render, and one scan reads Cursor's main script — megabytes of it — so
    /// the answer is reused while the question is identical. The two ways the answer can change are
    /// our own chords moving and the user coming back from the other app; both must still rescan, or
    /// this is the stale row the live query exists to avoid.
    func testTheScanIsReusedBetweenRendersButNotAcrossAChangeOrAnActivation() {
        var scans = 0
        let bindings = provider(scan: { _ in
            scans += 1
            return ShortcutConflicts.Report(findings: [:], conflicts: [])
        })

        _ = bindings.conflicts()
        _ = bindings.conflicts()
        XCTAssertEqual(scans, 1, "an unchanged question is not re-read from disk on every render")

        XCTAssertEqual(bindings.record(Self.optionCommandK, for: .openActivity), .recorded)
        _ = bindings.conflicts()
        XCTAssertEqual(scans, 2, "a rebind changes which chords are contested")

        // What the app-activation observer calls: the user may have just uninstalled the other tool.
        bindings.invalidateConflictScan()
        _ = bindings.conflicts()
        XCTAssertEqual(scans, 3)
    }

    /// Airgap Mode is the **third** thing that changes the answer, and the cache had no way to hear
    /// about it.
    ///
    /// `ShortcutConflicts.scan` short-circuits every tool to `.undetermined` while the switch is on —
    /// it will not open another app's configuration — and the switch is in this same pane. So neither
    /// existing invalidator can fire for it: our own chords do not move, and flipping a toggle in the
    /// window that is already frontmost never deactivates the app, so no `didBecomeActive` arrives.
    /// A user who turned Airgap Mode off *precisely so the app could check* got the cached "I can't
    /// tell" report for as long as the Settings window stayed open.
    ///
    /// The `notify()` the invalidation sends is what the expectation waits on, so this is
    /// deterministic rather than a sleep: the engine calls its observers on the thread that made the
    /// change and this one hops to the main actor.
    func testFlippingAirgapModeRescansBecauseTheScanIsTheThingAirgapWasSuppressing() async throws {
        let exclusions = try temporaryExclusions()
        var scans = 0
        let bindings = provider(
            scan: { _ in
                scans += 1
                return ShortcutConflicts.Report(findings: [:], conflicts: [])
            },
            exclusions: exclusions)

        _ = bindings.conflicts()
        _ = bindings.conflicts()
        XCTAssertEqual(scans, 1, "the cached answer is still reused between renders")

        // First the change that must *not* invalidate. The engine calls every observer on every
        // mutation, and re-reading Cursor's main script — megabytes, on the main thread — because
        // someone excluded an app is exactly the jank the cache exists to prevent.
        XCTAssertEqual(
            exclusions.setExcluded(true, bundleID: "com.example.some-app"), .applied)
        // A barrier, not a sleep: the engine calls its observers synchronously before `setExcluded`
        // returns, so the provider's main-actor hop is already enqueued when this one is, and equal
        // priority jobs on the main actor run in the order they were enqueued.
        await Task { @MainActor in }.value
        _ = bindings.conflicts()
        XCTAssertEqual(
            scans, 1, "excluding an app is not a reason to re-read another app's configuration")

        let switchedOn = expectation(description: "the pane is told Airgap Mode changed")
        var token = bindings.addObserver { switchedOn.fulfill() }
        XCTAssertEqual(exclusions.setAirgapMode(true), .applied)
        await fulfillment(of: [switchedOn], timeout: 5)
        bindings.removeObserver(token)

        XCTAssertEqual(scans, 1, "the report is dropped, not re-run — the pane's next render runs it")
        _ = bindings.conflicts()
        XCTAssertEqual(scans, 2, "the switch moved, so the answer it decides is asked again")

        // The direction that actually matters: off again, and the app may look at the other tools'
        // configuration once more.
        let switchedOff = expectation(description: "the pane is told Airgap Mode changed back")
        token = bindings.addObserver { switchedOff.fulfill() }
        XCTAssertEqual(exclusions.setAirgapMode(false), .applied)
        await fulfillment(of: [switchedOff], timeout: 5)
        bindings.removeObserver(token)

        _ = bindings.conflicts()
        XCTAssertEqual(scans, 3, "turning it off is the whole reason a user would turn it off")
    }
}

// MARK: - Key labels

final class ShortcutKeyLabelTests: XCTestCase {

    /// Space prints a space and Delete prints nothing at all; both are unreadable in a recorder, so
    /// they are named rather than translated.
    func testKeysThatPrintNothingLegibleGetANameAheadOfTheLayout() {
        XCTAssertEqual(ShortcutKeyLabel.label(for: 49, printing: { _ in " " }), "Space")
        XCTAssertEqual(ShortcutKeyLabel.label(for: 51, printing: { _ in nil }), "⌫")
        XCTAssertEqual(ShortcutKeyLabel.label(for: 123, printing: { _ in nil }), "←")
    }

    /// A key code is not a letter: the same code is `K` on US and `T` on Dvorak, so the label comes
    /// from the layout and is upper-cased to match what the recorder stores off an event.
    func testAnOrdinaryKeyTakesItsLabelFromTheLayout() {
        XCTAssertEqual(ShortcutKeyLabel.label(for: 40, printing: { _ in "k" }), "K")
        XCTAssertEqual(ShortcutKeyLabel.label(for: 40, printing: { _ in "t" }), "T")
    }

    /// Several input methods carry no Unicode layout data at all. A code printed as a code is ugly
    /// and true; a guessed letter would be pretty and wrong.
    func testAnUntranslatableKeyPrintsItsCode() {
        XCTAssertEqual(ShortcutKeyLabel.label(for: 40, printing: { _ in nil }), "Key 40")
        XCTAssertEqual(ShortcutKeyLabel.label(for: 40, printing: { _ in "  " }), "Key 40")
    }

    /// The recorder and the menu bar describe the same keystroke, so they have to spell it the same
    /// way. A recorded chord prints in macOS's order; the gesture default does not, because
    /// `⌘ + ⌘` is a gesture and not a modifier list.
    func testARecordedChordPrintsTheWayTheRestOfMacOSPrintsIt() {
        let controlCommandSpace = SettingsShortcutChord(keyCode: 49, modifierFlags: [.command, .control])
        XCTAssertEqual(controlCommandSpace.displayString, "⌃⌘Space")
        XCTAssertEqual(
            controlCommandSpace.displayString,
            ShortcutChord.key(label: "Space", modifiers: [.command, .control]).display,
            "Settings and the shortcut layer must not spell one shortcut two ways")
        XCTAssertEqual(ShortcutAction.openActivity.defaultChord.displayString, "⌘ + ⌘")
    }
}
