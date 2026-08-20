import AppKit
import ContextCore
import Foundation

// MARK: - The slice of the shortcut layer this adapter needs

/// What `LiveShortcutBindings` uses `GlobalShortcuts` for, and nothing else.
///
/// Exists so the adapter's rules — what a valid chord is, what happens when registration is refused,
/// what a cleared slot means — can be asserted without a test process registering a system-wide hot
/// key. `RegisterEventHotKey` is a real, machine-wide side effect: a suite that took ⌘⌥K on the
/// machine running it would be neither hermetic nor polite, and on a headless runner it would report
/// whatever that machine's other software happens to hold. Every member below already exists on
/// `GlobalShortcuts` with this exact signature, so the conformance is empty by construction.
@MainActor
protocol ShortcutRegistry: AnyObject {
    func binding(for action: GlobalShortcuts.Action) -> GlobalShortcuts.Binding
    func setRecorded(_ recorded: GlobalShortcuts.Recorded?, for action: GlobalShortcuts.Action)
    func readiness(for action: GlobalShortcuts.Action) -> GlobalShortcuts.Readiness
    func armedChords() -> [GlobalShortcuts.Action: ShortcutChord]
}

extension GlobalShortcuts: ShortcutRegistry {}

// MARK: - The provider

/// Settings' two recorders, wired to the hot keys that actually fire.
///
/// The General pane talks to `ShortcutBindingProvider`; the system-wide shortcuts live in
/// `GlobalShortcuts`; the "Codex also uses ⌘ + ⌘" row comes from `ShortcutConflicts`. This is the only
/// thing joining the three, and it is deliberately thin — no state of its own beyond the remedies it
/// has to remember between rendering a row and the user pressing its button. Everything the pane
/// asks about is read back out of the store on demand, so a shortcut changed anywhere (another
/// window, a `defaults write`, a cleared slot) is what the pane shows.
///
/// Two properties of the seam are load-bearing and easy to lose:
///
/// - **A recorded chord is armed before `record` returns.** `GlobalShortcuts.setRecorded` persists
///   and then re-registers, so the new shortcut works immediately. A provider that only wrote to
///   `UserDefaults` would look identical in Settings and do nothing until the next launch.
/// - **`binding(for:)` is nil unless the user recorded something.** The pane reads nil as *cleared*
///   and hides the ✕ — so a virgin install, which is on the gesture default and has nothing to
///   clear, must not report that default as a recorded binding.
@MainActor
final class LiveShortcutBindings: ShortcutBindingProvider {

    private let registry: ShortcutRegistry
    /// Key code → what that key prints here. Injected so a test can pin a layout.
    private let label: (UInt16) -> String
    /// The conflict scan, as a function of the chords that are live right now.
    private let scan: ([GlobalShortcuts.Action: ShortcutChord]) -> ShortcutConflicts.Report

    /// The remedy behind each row on screen, keyed by `SettingsShortcutConflict.id`.
    ///
    /// `SettingsShortcutConflict` carries a button *title* and no action — deliberately, so a view
    /// can diff it — so the thing the button does has to live here. Rebuilt on every `conflicts()`
    /// call, which is also every render: a remedy for a row that is no longer shown is stale by
    /// definition.
    private var remedies: [String: ShortcutConflicts.Remedy] = [:]
    private var observers: [UUID: @MainActor () -> Void] = [:]

    /// The last scan, and the chords it was run against.
    ///
    /// `conflicts()` is called from the pane's `body`, so it runs on every render — and one scan
    /// reads Cursor's main script, which is megabytes. Re-reading that on the main thread every time
    /// a toggle flips is jank the user feels for a question whose answer almost never changes.
    ///
    /// Nothing is *persisted*, which is the property the pane's live query exists to protect: this
    /// dies with the object, is dropped the moment our own chords move, and is dropped again on every
    /// activation — the one moment the user could have come back from uninstalling or reconfiguring
    /// the other tool. A stored flag would outlive the conflict; this cannot outlive the window.
    private var lastScan: (chords: [GlobalShortcuts.Action: ShortcutChord], report: ShortcutConflicts.Report)?
    private var activationObserver: NSObjectProtocol?

    private let exclusions: ExclusionEngine

    /// Airgap Mode: the third thing that changes the answer, and the one that was missing.
    ///
    /// `ShortcutConflicts.scan` short-circuits every tool to `.undetermined` while Airgap Mode is on
    /// — it will not open another app's configuration — and the Airgap switch is in *this pane*.
    /// So neither invalidator above can reach it: our chords did not move, and flipping a toggle in
    /// the window that is already frontmost never deactivates the app, so no `didBecomeActive`
    /// arrives. A user who turned Airgap off precisely so the app could check got the cached
    /// "I can't tell" report for as long as the window stayed open.
    ///
    /// `lastAirgapMode` is why only an *airgap* change invalidates: the engine calls the handler on
    /// every mutation, and re-reading Cursor's main script — megabytes, on the main thread — because
    /// the user excluded an app is exactly the jank `lastScan` exists to prevent.
    private var exclusionObserver: UUID?
    private var lastAirgapMode: Bool?

    /// - Parameter registry: nil means the app's own shortcut layer. Resolved in the body rather than
    ///   as a default argument because default arguments are evaluated outside the main actor, and
    ///   `GlobalShortcuts.shared` is isolated to it.
    /// - Parameter exclusions: the engine to watch Airgap Mode on. A parameter rather than a straight
    ///   reach for `.shared` so a test can flip the switch on a throwaway configuration file instead
    ///   of on the developer's own — `ExclusionEngine` is nonisolated, so this one *can* be a default
    ///   argument.
    init(
        registry: ShortcutRegistry? = nil,
        label: @escaping (UInt16) -> String = { ShortcutKeyLabel.label(for: $0) },
        // The default parameter of `scan` reads `ExclusionEngine.shared.current.airgapMode`, which is
        // how Airgap Mode reaches this surface: with it on, nothing here opens another app's config
        // and the scan says it cannot tell. There is no second flag for it, here or anywhere.
        scan: @escaping ([GlobalShortcuts.Action: ShortcutChord]) -> ShortcutConflicts.Report = {
            ShortcutConflicts.scan(ours: $0)
        },
        exclusions: ExclusionEngine = .shared
    ) {
        self.registry = registry ?? GlobalShortcuts.shared
        self.label = label
        self.scan = scan
        self.exclusions = exclusions
        // Another app's shortcut is changed in that app, and the only reliable signal that happened
        // is the user coming back to us. `GlobalShortcuts` re-registers on the same notification.
        //
        // `notify()` as well as the invalidation, because coming back is also the one moment
        // `readiness(for:)` can have changed: Accessibility is granted in System Settings, macOS
        // posts nothing when it happens, and returning to this app is the whole of the signal. A
        // pane that dropped its cached conflict report but kept printing "needs Accessibility" over
        // a grant the user had just given would be telling them their work did not land.
        activationObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.didBecomeActiveNotification, object: nil, queue: .main
        ) { [weak self] _ in
            MainActor.assumeIsolated {
                self?.invalidateConflictScan()
                self?.notify()
            }
        }
        // Seeded before registering, because `addObserver` calls back immediately with the current
        // set: without this the first callback would read as a change and fire a render nobody
        // asked for. The engine calls later ones on whichever thread made the change, so hop.
        lastAirgapMode = exclusions.current.airgapMode
        exclusionObserver = exclusions.addObserver { [weak self] set in
            let airgapMode = set.airgapMode
            Task { @MainActor in self?.airgapModeChanged(to: airgapMode) }
        }
    }

    deinit {
        if let activationObserver { NotificationCenter.default.removeObserver(activationObserver) }
        if let exclusionObserver { exclusions.removeObserver(exclusionObserver) }
    }

    /// Drops the cached report when — and only when — Airgap Mode actually moved.
    private func airgapModeChanged(to airgapMode: Bool) {
        guard lastAirgapMode != airgapMode else { return }
        lastAirgapMode = airgapMode
        invalidateConflictScan()
        notify()
    }

    // MARK: Bindings

    func binding(for action: ShortcutAction) -> SettingsShortcutChord? {
        // `.gestureDefault` is *not* a recorded chord. Returning the default here would light the
        // "✕ clear" button on a machine where nothing was ever recorded, offering to clear a slot
        // that is already clear.
        guard case .recorded(let recorded) = registry.binding(for: registryAction(action)) else {
            return nil
        }
        return SettingsShortcutChord(keyCode: recorded.keyCode, modifierFlags: recorded.modifiers.appKitFlags)
    }

    /// The shortcut layer's own answer, translated. Read live rather than cached: Accessibility is
    /// granted in System Settings while this app runs, and `GlobalShortcuts.readiness` computes
    /// `AXElement.isTrusted` at the moment it is asked — so a pane that re-renders after the user
    /// comes back from that pane shows the new answer without anything having to be told.
    func readiness(for action: ShortcutAction) -> ShortcutReadiness {
        switch registry.readiness(for: registryAction(action)) {
        case .armed: return .armed
        case .needsAccessibility: return .needsAccessibility
        case .rejected(let reason): return .rejected(reason)
        }
    }

    func record(_ chord: SettingsShortcutChord, for action: ShortcutAction) -> ShortcutRecordResult {
        // Normalised first: the recorder masks with `deviceIndependentFlagsMask`, which still carries
        // Caps Lock and Fn. Comparing or storing an unnormalised chord would make the same keypress
        // record differently depending on whether Caps Lock happened to be on.
        let modifiers = ShortcutModifiers(chord.modifiers)
        guard let keyCode = chord.keyCode else {
            // Only reachable if some future recorder sends a modifier-only chord. `RegisterEventHotKey`
            // has nothing to take from one, and the gesture defaults (`⌘ + ⌘`, `⌘⌘⇧`) are not
            // user-recordable: asking for one is what *clearing* the slot does.
            return .rejected("Hold a modifier and press a key.")
        }
        let normalized = SettingsShortcutChord(keyCode: keyCode, modifierFlags: modifiers.appKitFlags)
        let display = normalized.displayString

        guard !modifiers.subtracting(.shift).isEmpty else {
            // ⇧K is K to every other app on the machine, so binding it would eat a letter everywhere.
            return .rejected("Add ⌘, ⌥ or ⌃ — ⇧ on its own is not a shortcut.")
        }
        guard !GlobalShortcuts.Recorded.unrecordableKeyCodes.contains(keyCode) else {
            return .rejected("\(display) is reserved — ⎋ and ↵ mean something in every app.")
        }
        guard !SettingsShortcutChord.reservedByMacOS.contains(normalized) else {
            return .rejected("macOS reserves \(display).")
        }
        if let other = ShortcutAction.allCases.first(where: { $0 != action && binding(for: $0) == normalized }
        ) {
            return .rejected("\(other.title) already uses \(display).")
        }

        let target = registryAction(action)
        let previous = recorded(for: target)
        // Persists *and* re-registers: `setRecorded` calls back into registration, so the chord is
        // live the moment this returns. Nothing here waits for a relaunch.
        registry.setRecorded(
            GlobalShortcuts.Recorded(keyCode: keyCode, modifiers: modifiers, label: label(keyCode)),
            for: target)

        if case .rejected(let reason) = registry.readiness(for: target) {
            // macOS refused it — almost always because another app already holds the chord. Keeping
            // the refused binding would leave the user with a shortcut that is stored, shown in the
            // recorder, and dead: the hot key is not registered and the gesture monitor no longer
            // answers for this action either. So put back what was working and say what happened;
            // the pane prints the reason under the row.
            registry.setRecorded(previous, for: target)
            return .rejected(reason)
        }

        notify()
        return .recorded
    }

    func clear(_ action: ShortcutAction) {
        // Back to the gesture default, and re-armed on the way — `setRecorded(nil,…)` is what puts
        // the `flagsChanged` monitor back, which is the half a plain "delete the key" would miss.
        registry.setRecorded(nil, for: registryAction(action))
        notify()
    }

    // MARK: Conflicts

    func conflicts() -> [SettingsShortcutConflict] {
        // Only the chords that are actually armed. A binding macOS refused, or a gesture default
        // with no Accessibility grant, is not a chord anyone else can be in the way of.
        let armed = registry.armedChords()
        let report: ShortcutConflicts.Report
        if let lastScan, lastScan.chords == armed {
            report = lastScan.report
        } else {
            report = scan(armed)
            lastScan = (armed, report)
        }

        var found: [String: ShortcutConflicts.Remedy] = [:]
        let rows = report.conflicts.map { conflict -> SettingsShortcutConflict in
            let action = settingsAction(conflict.action)
            let row = SettingsShortcutConflict(
                action: action,
                owner: conflict.tool.name,
                // Our own chord, taken from the store rather than converted from `conflict.chord`:
                // the scan's vocabulary carries a printed key *label* and this one needs a key code,
                // and the two are the same shortcut by construction — the scan only reports an
                // overlap against a chord we handed it.
                chord: binding(for: action) ?? action.defaultChord,
                // Never "Switch Codex to ⌥⌥": `ShortcutConflicts.Remedy` explains at length why this
                // app does not rewrite another product's configuration. Revealing the file it read is
                // the only thing one click can honestly do.
                remedyTitle: conflict.remedy.revealPath == nil ? nil : "Reveal in Finder",
                detail: "\(conflict.evidence.sentence) \(conflict.remedy.instruction)")
            found[row.id] = conflict.remedy
            return row
        }
        remedies = found
        return rows
    }

    /// Forces the next `conflicts()` to read the other tools' configuration again.
    func invalidateConflictScan() {
        lastScan = nil
    }

    func resolve(_ conflict: SettingsShortcutConflict) {
        // No `notify()`: revealing a file changes nothing about the collision, and the row is
        // supposed to stay until one side's shortcut actually moves.
        remedies[conflict.id]?.reveal()
    }

    // MARK: Observers

    @discardableResult
    func addObserver(_ handler: @escaping @MainActor () -> Void) -> UUID {
        let id = UUID()
        observers[id] = handler
        return id
    }

    func removeObserver(_ id: UUID) {
        observers[id] = nil
    }

    private func notify() {
        for handler in observers.values { handler() }
    }

    // MARK: Plumbing

    private func recorded(for action: GlobalShortcuts.Action) -> GlobalShortcuts.Recorded? {
        guard case .recorded(let recorded) = registry.binding(for: action) else { return nil }
        return recorded
    }

    /// The two enums are the same action with the same raw value, but matched by `switch` rather
    /// than by `init(rawValue:)`: adding a second shortcut to either one should fail to compile
    /// here, not return nil at runtime and drop a row out of Settings.
    private func registryAction(_ action: ShortcutAction) -> GlobalShortcuts.Action {
        switch action {
        case .openActivity: return .openActivity
        }
    }

    private func settingsAction(_ action: GlobalShortcuts.Action) -> ShortcutAction {
        switch action {
        case .openActivity: return .openActivity
        }
    }
}
