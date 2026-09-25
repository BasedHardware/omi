import AppKit
import Foundation

// MARK: - The chord

/// One recorded shortcut, in the only shape a recorder can actually produce.
///
/// `keyCode` is optional because the two defaults this app ships — `⌘ + ⌘` and `⌘⌘⇧` — have no key
/// at all: they are gestures made out of modifiers, which is why `gesture` exists as a field rather
/// than being implied. A model that could only express "modifiers + key" could not represent the
/// app's own defaults, so it would have been wrong before the first row was drawn.
struct SettingsShortcutChord: Equatable, Hashable, Codable, Sendable {
    /// What the user's hands do. One field rather than a tap count plus a flag, because the three
    /// are alternatives and no pair of them is a thing: a chord cannot be tapped twice *and* be the
    /// two Command keys, and a state that can spell that is a state something has to check.
    enum Gesture: String, Equatable, Hashable, Codable, Sendable {
        /// Hold the modifiers, strike the key. Everything a recorder can produce.
        case press
        /// Tap the primary modifier twice, with any others held across both halves.
        case doubleTap
        /// Press the two physical Command keys together. Not a modifier set — see
        /// `ShortcutChord.bothCommandKeys` for why one cannot describe it.
        case bothCommandKeys
    }

    /// Virtual key code, or nil for a modifier-only chord.
    var keyCode: UInt16?
    /// `NSEvent.ModifierFlags.rawValue`, already masked to `deviceIndependentFlagsMask`.
    var modifierFlags: UInt
    var gesture: Gesture

    init(keyCode: UInt16? = nil, modifierFlags: NSEvent.ModifierFlags, gesture: Gesture = .press) {
        self.keyCode = keyCode
        self.modifierFlags = modifierFlags.intersection(.deviceIndependentFlagsMask).rawValue
        self.gesture = gesture
    }

    var modifiers: NSEvent.ModifierFlags {
        NSEvent.ModifierFlags(rawValue: modifierFlags).intersection(.deviceIndependentFlagsMask)
    }

    /// `⌘ + ⌘`, `⌘⌘⇧`, `⌥⌥`, `⌘⇧K`. In the order macOS prints modifiers: ⌃⌥⇧⌘.
    ///
    /// A double-tap repeats the *primary* modifier and then appends the rest, because `⌘⌘⇧` is what
    /// the reference shows and `⌘⇧⌘⇧` is not a thing anyone writes. The two Command keys are the one
    /// gesture this cannot build out of the modifier set it holds, so it takes the spelling from the
    /// shortcut layer instead — see below.
    var displayString: String {
        let flags = modifiers
        let key = keyCode.flatMap(Self.keyName) ?? ""

        switch gesture {
        case .bothCommandKeys:
            // Spelled once, in `ShortcutChord`, and read from there: the recorder, the menu bar and
            // the conflict row all describe this one gesture, and `⌘ + ⌘` on one surface next to
            // `⌘⌘` on another would read as two different shortcuts. `⌘⌘` in particular is *taken* —
            // it is the search default's first two glyphs.
            return ShortcutChord.bothCommandKeysDisplay

        case .press:
            // An ordinary chord prints the way macOS prints one, which is also what
            // `ShortcutChord.display` gives the menu bar and the conflict scanner for the same
            // shortcut: two spellings of one keystroke on two surfaces is a bug the user reads as
            // "these are different shortcuts".
            var out = ""
            for (flag, symbol) in Self.systemOrder where flags.contains(flag) { out += symbol }
            return out + key

        case .doubleTap:
            var primary = ""
            var rest = ""
            // Primary is the outermost modifier present, which is the one a user taps.
            for (flag, symbol) in Self.tapOrder where flags.contains(flag) {
                if primary.isEmpty {
                    primary = symbol
                } else {
                    rest += symbol
                }
            }
            guard !primary.isEmpty else { return key }
            return primary + primary + rest + key
        }
    }

    /// The chord said out loud, for an accessibility label or for copy that has to teach the
    /// gesture. Delegates to `ShortcutChord`, so the words and the glyphs are decided in one place.
    var spokenDescription: String {
        switch gesture {
        case .bothCommandKeys: return ShortcutChord.bothCommandKeysPhrase
        default: return displayString
        }
    }

    /// Apple's order: ⌃⌥⇧⌘, which is the order every macOS menu prints them in.
    private static let systemOrder: [(NSEvent.ModifierFlags, String)] = [
        (.control, "⌃"), (.option, "⌥"), (.shift, "⇧"), (.command, "⌘"),
    ]

    /// `⌘` before `⇧` here, unlike AppKit's print order, because the primary modifier is picked off
    /// the front of this list and `⌘` is the one the app's own defaults tap.
    private static let tapOrder: [(NSEvent.ModifierFlags, String)] = [
        (.command, "⌘"), (.option, "⌥"), (.control, "⌃"), (.shift, "⇧"),
    ]

    /// The label the key carries on this Mac's layout.
    ///
    /// `↵` is spelled here rather than in `ShortcutKeyLabel` because Return is not recordable —
    /// nothing can bind it — but the default table below can still be asked to print one.
    private static func keyName(_ code: UInt16) -> String {
        switch code {
        case 36: "↵"
        case 53: "⎋"
        // Everything else goes to the shortcut layer, which asks the current keyboard layout. A table
        // of key codes here would print `K` for a Dvorak user's `T`.
        default: ShortcutKeyLabel.label(for: code)
        }
    }

    /// Chords macOS will never hand an app, so a recorder that accepted one would produce a shortcut
    /// that silently never fires. Shared by the live provider and the in-memory stand-in: two lists
    /// would mean the stub proving a refusal the real recorder does not make.
    static let reservedByMacOS: [SettingsShortcutChord] = [
        SettingsShortcutChord(keyCode: 12, modifierFlags: .command),  // ⌘Q
        SettingsShortcutChord(keyCode: 48, modifierFlags: .command),  // ⌘Tab
        SettingsShortcutChord(keyCode: 49, modifierFlags: .command),  // ⌘Space
    ]
}

// MARK: - The slots

/// The shortcut the General pane records.
///
/// The mirror of `GlobalShortcuts.Action`, and `openActivity` carries the same rename for the same
/// reason: the chord opens the Activity window rather than the timeline, so a slot that still said
/// timeline would be a recorder describing a window it does not summon. Nothing here is persisted —
/// `rawValue` is only this pane's `Identifiable` id and half of a conflict row's — so unlike the
/// shortcut layer's own case, this one had no stored name to leave behind.
///
/// **`openSearch` is gone, and the pane is why it had to go from here too.** It bound a second
/// chord to the same window (`ContextApp.shortcutFired` answered both with one `window.press()`),
/// so the pane drew two recorders for one behaviour — see `GlobalShortcuts.Action`.
enum ShortcutAction: String, CaseIterable, Identifiable, Sendable {
    case openActivity

    var id: String { rawValue }

    var title: String {
        switch self {
        case .openActivity: "Open Activity Shortcut"
        }
    }

    /// Reference copy, with our own default chord named in it.
    var subtitle: String {
        "Record a keyboard shortcut. Clear it to use \(defaultChord.displayString)."
    }

    /// What the app falls back to when the slot is cleared.
    ///
    /// The same chord `GlobalShortcuts.Action.defaultChord` names, in this pane's vocabulary — the
    /// two Command keys pressed together. The two are asserted against each other in the tests,
    /// because a recorder showing a gesture the shortcut layer does not listen for is worse than
    /// showing nothing.
    var defaultChord: SettingsShortcutChord {
        switch self {
        case .openActivity: SettingsShortcutChord(modifierFlags: .command, gesture: .bothCommandKeys)
        }
    }

    /// A clock rewinding stood here for `openActivity`, and it was drawn for the timeline. The row
    /// opens the day's stream of what happened, so it gets the glyph for a list of entries.
    var symbol: String {
        switch self {
        case .openActivity: "list.bullet.rectangle"
        }
    }
}

// MARK: - Conflicts

/// Another tool on this Mac that has claimed the same chord.
///
/// `remedyTitle` is a string rather than a closure so this stays `Equatable` and a view can diff it;
/// applying it goes back through the provider, which is the only thing that knows how to rewrite
/// somebody else's configuration.
struct SettingsShortcutConflict: Equatable, Identifiable, Sendable {
    let action: ShortcutAction
    /// The other tool's display name, e.g. `Codex`.
    let owner: String
    let chord: SettingsShortcutChord
    /// One-click switch, e.g. `Switch Codex to ⌥⌥`. Nil when nothing can be done automatically, in
    /// which case the row states the clash and offers no button.
    let remedyTitle: String?
    /// Where the claim came from and what to change, from whoever detected the clash.
    ///
    /// Optional, and appended rather than baked into `subtitle`, because "Codex's keymap says so" and
    /// "this is what Codex falls back to" are not the same strength of claim — a row that cannot say
    /// which one it rests on is asking the user to take its word for it.
    let detail: String?

    init(
        action: ShortcutAction,
        owner: String,
        chord: SettingsShortcutChord,
        remedyTitle: String?,
        detail: String? = nil
    ) {
        self.action = action
        self.owner = owner
        self.chord = chord
        self.remedyTitle = remedyTitle
        self.detail = detail
    }

    var id: String { "\(action.rawValue)/\(owner)" }

    /// Reference copy shape: `Codex also uses ⌘ + ⌘` / `Context for Claude and Codex both use ⌘ + ⌘.`
    var title: String { "\(owner) also uses \(chord.displayString)" }

    var subtitle: String {
        let claim = "Context for Claude and \(owner) both use \(chord.displayString)."
        guard let detail, !detail.isEmpty else { return claim }
        return "\(claim) \(detail)"
    }
}

enum ShortcutRecordResult: Equatable, Sendable {
    case recorded
    /// The chord is reserved by the system (⌘Q, ⌘Tab) or already used by the other slot.
    case rejected(String)
}

// MARK: - Whether the chord in the recorder will actually fire

/// What the recorder is allowed to imply about the chord printed in it.
///
/// The mirror of `GlobalShortcuts.Readiness` in this pane's vocabulary, and it exists because the
/// recorder had no way to ask. `GlobalShortcuts.readiness(for:)` was written for exactly this — its
/// own documentation says the gesture defaults "cannot be registered as hot keys at all … macOS gates
/// [the monitor] behind Accessibility. When that grant is missing the shortcut does not fire, and
/// `readiness(for:)` says so rather than letting Settings imply otherwise" — but the seam this pane
/// talks through had no member for it, so Settings never asked and printed `⌘ + ⌘` on a Mac where
/// pressing it did nothing at all. A recorder showing a chord that cannot fire is the same defect as
/// a control that silently does nothing; it is worse, because the user has evidence for the opposite.
enum ShortcutReadiness: Equatable, Sendable {
    /// Registered, or watched for, and it will fire.
    case armed
    /// A gesture binding on a Mac that has not granted Accessibility. Nothing fires.
    case needsAccessibility
    /// macOS refused the recorded key equivalent — almost always because something else holds it.
    case rejected(String)

    var isArmed: Bool { self == .armed }

    /// The line printed under the row. Nil when there is nothing wrong to say.
    ///
    /// Named here rather than in the view so the copy is assertable: this is the only warning the
    /// user gets that a shortcut they can *see* does not work.
    var note: String? {
        switch self {
        case .armed: return nil
        case .needsAccessibility:
            return "This shortcut needs Accessibility to fire. Until it is granted, pressing it does nothing."
        case .rejected(let reason): return reason
        }
    }
}

// MARK: - The seam

/// What the General pane needs from the global-shortcut layer, and nothing else.
///
/// The shortcut layer (`Sources/ContextApp/Shortcuts/*`) is being built separately and did not exist
/// when this pane was written, so the pane depends on this protocol rather than on that layer. Three
/// things about the shape are load-bearing:
///
/// - **`binding(for:)` returns an optional.** Nil is *cleared*, which the reference copy makes a real
///   state ("Clear it to use ⌘ + ⌘") rather than an error — a cleared slot falls back to
///   `ShortcutAction.defaultChord`, and the recorder shows that chord greyed.
/// - **`record` can refuse.** A recorder that always succeeds would let the user bind ⌘Q.
/// - **Conflicts are queried, never stored.** `I3` requires the row to appear *only* on a real
///   conflict, which means a live check against other installed tools every time the pane appears —
///   a persisted flag would leave the row on screen after the user uninstalled the other tool.
@MainActor
protocol ShortcutBindingProvider: AnyObject {
    /// The chord in force for `action`, or nil when the slot is cleared.
    func binding(for action: ShortcutAction) -> SettingsShortcutChord?
    /// Whether the chord the recorder is about to print will actually fire. Read on every render —
    /// Accessibility is granted outside this process and macOS posts nothing when it happens.
    func readiness(for action: ShortcutAction) -> ShortcutReadiness
    /// Live check. Empty when nothing clashes, which is the common case.
    func conflicts() -> [SettingsShortcutConflict]
    func record(_ chord: SettingsShortcutChord, for action: ShortcutAction) -> ShortcutRecordResult
    func clear(_ action: ShortcutAction)
    /// Applies `conflict.remedyTitle`'s promise. A no-op when the remedy was nil.
    func resolve(_ conflict: SettingsShortcutConflict)
    /// Called whenever any of the above would answer differently. Mirrors
    /// `ExclusionEngine.addObserver` so both live surfaces on these panes observe the same way.
    @discardableResult
    func addObserver(_ handler: @escaping @MainActor () -> Void) -> UUID
    func removeObserver(_ id: UUID)
}

/// The in-memory stand-in: a test double, and the value the window holds before launch swaps in the
/// real one.
///
/// It registers **nothing** with the system, and says so: a stub that pretended to install a global
/// hotkey would make the pane look finished while `⌘ + ⌘` did nothing, which is the failure mode `J7`
/// names. The real provider is `LiveShortcutBindings`, assigned to `SettingsWindow.shortcutProvider`
/// in `ContextApp` beside `GlobalShortcuts.shared.start(…)` — this one keeps real state so the
/// recorder, the cleared state and the rejection path stay exercisable without a hot key.
///
/// It seeds both slots with the default chord, which the live provider deliberately does not: for
/// this class that is the fixture the pane's tests want, but from the store a virgin install has no
/// recorded binding at all and must report nil so the "✕ clear" button stays hidden.
@MainActor
final class InMemoryShortcutBindings: ShortcutBindingProvider {

    private var chords: [ShortcutAction: SettingsShortcutChord]
    private var declaredConflicts: [SettingsShortcutConflict]
    private var observers: [UUID: @MainActor () -> Void] = [:]

    /// Overridden per slot by a test that wants the ungranted-Accessibility row. `.armed` everywhere
    /// else, because this stand-in registers nothing and so has nothing that can be refused.
    var declaredReadiness: [ShortcutAction: ShortcutReadiness]

    init(
        chords: [ShortcutAction: SettingsShortcutChord]? = nil,
        conflicts: [SettingsShortcutConflict] = [],
        readiness: [ShortcutAction: ShortcutReadiness] = [:]
    ) {
        self.chords =
            chords
            ?? Dictionary(uniqueKeysWithValues: ShortcutAction.allCases.map { ($0, $0.defaultChord) })
        self.declaredConflicts = conflicts
        self.declaredReadiness = readiness
    }

    func binding(for action: ShortcutAction) -> SettingsShortcutChord? { chords[action] }

    func readiness(for action: ShortcutAction) -> ShortcutReadiness {
        declaredReadiness[action] ?? .armed
    }

    func conflicts() -> [SettingsShortcutConflict] { declaredConflicts }

    func record(_ chord: SettingsShortcutChord, for action: ShortcutAction) -> ShortcutRecordResult {
        if SettingsShortcutChord.reservedByMacOS.contains(chord) {
            return .rejected("macOS reserves \(chord.displayString).")
        }
        if let other = ShortcutAction.allCases.first(where: { $0 != action && chords[$0] == chord }) {
            return .rejected("\(other.title) already uses \(chord.displayString).")
        }
        chords[action] = chord
        notify()
        return .recorded
    }

    func clear(_ action: ShortcutAction) {
        chords[action] = nil
        notify()
    }

    func resolve(_ conflict: SettingsShortcutConflict) {
        guard conflict.remedyTitle != nil else { return }
        declaredConflicts.removeAll { $0.id == conflict.id }
        notify()
    }

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
}
