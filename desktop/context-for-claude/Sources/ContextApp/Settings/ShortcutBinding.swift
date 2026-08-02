import AppKit
import Foundation

// MARK: - The chord

/// One recorded shortcut, in the only shape a recorder can actually produce.
///
/// `keyCode` is optional because the two defaults this app ships — `⌘⌘` and `⌘⌘⇧` — have no key at
/// all: they are a *modifier tapped twice*, which is why `tapCount` exists as a field rather than
/// being implied. A model that could only express "modifiers + key" could not represent the app's own
/// defaults, so it would have been wrong before the first row was drawn.
struct SettingsShortcutChord: Equatable, Hashable, Codable, Sendable {
    /// Virtual key code, or nil for a modifier-only chord.
    var keyCode: UInt16?
    /// `NSEvent.ModifierFlags.rawValue`, already masked to `deviceIndependentFlagsMask`.
    var modifierFlags: UInt
    /// 1 for an ordinary chord, 2 for a double-tap of the modifier set.
    var tapCount: Int

    init(keyCode: UInt16? = nil, modifierFlags: NSEvent.ModifierFlags, tapCount: Int = 1) {
        self.keyCode = keyCode
        self.modifierFlags = modifierFlags.intersection(.deviceIndependentFlagsMask).rawValue
        self.tapCount = max(1, tapCount)
    }

    var modifiers: NSEvent.ModifierFlags {
        NSEvent.ModifierFlags(rawValue: modifierFlags).intersection(.deviceIndependentFlagsMask)
    }

    /// `⌘⌘`, `⌘⌘⇧`, `⌥⌥`, `⌘⇧K`. In the order macOS prints modifiers: ⌃⌥⇧⌘.
    ///
    /// A double-tap repeats the *primary* modifier and then appends the rest, because `⌘⌘⇧` is what
    /// the reference shows and `⌘⇧⌘⇧` is not a thing anyone writes.
    var displayString: String {
        let flags = modifiers
        var primary = ""
        var rest = ""
        // Primary is the outermost modifier present, which is the one a user taps.
        for (flag, symbol) in Self.symbolOrder where flags.contains(flag) {
            if primary.isEmpty {
                primary = symbol
            } else {
                rest += symbol
            }
        }
        guard !primary.isEmpty else { return keyCode.flatMap(Self.keyName) ?? "" }
        let tapped = String(repeating: primary, count: tapCount)
        let key = keyCode.flatMap(Self.keyName) ?? ""
        return tapped + rest + key
    }

    /// `⌘` before `⇧` here, unlike AppKit's print order, because the primary modifier is picked off
    /// the front of this list and `⌘` is the one the app's own defaults tap.
    private static let symbolOrder: [(NSEvent.ModifierFlags, String)] = [
        (.command, "⌘"), (.option, "⌥"), (.control, "⌃"), (.shift, "⇧"),
    ]

    /// Only the keys a recorder can plausibly capture and print without a keyboard-layout lookup.
    /// Anything else prints as its code, which is ugly and true rather than pretty and wrong.
    private static func keyName(_ code: UInt16) -> String {
        switch code {
        case 36: "↵"
        case 48: "⇥"
        case 49: "Space"
        case 53: "⎋"
        case 51: "⌫"
        case 123: "←"
        case 124: "→"
        case 125: "↓"
        case 126: "↑"
        default:
            // `UCKeyTranslate` is the correct answer and needs the current layout, which the
            // shortcut layer owns. Until then a code is printed as a code.
            "Key \(code)"
        }
    }
}

// MARK: - The slots

/// The two shortcuts the General pane records.
enum ShortcutAction: String, CaseIterable, Identifiable, Sendable {
    case openTimeline
    case openSearch

    var id: String { rawValue }

    var title: String {
        switch self {
        case .openTimeline: "Open Timeline Shortcut"
        case .openSearch: "Open Search Shortcut"
        }
    }

    /// Reference copy, with our own default chord named in it.
    var subtitle: String {
        "Record a keyboard shortcut. Clear it to use \(defaultChord.displayString)."
    }

    /// What the app falls back to when the slot is cleared.
    var defaultChord: SettingsShortcutChord {
        switch self {
        case .openTimeline: SettingsShortcutChord(modifierFlags: .command, tapCount: 2)
        case .openSearch: SettingsShortcutChord(modifierFlags: [.command, .shift], tapCount: 2)
        }
    }

    var symbol: String {
        switch self {
        case .openTimeline: "clock.arrow.circlepath"
        case .openSearch: "magnifyingglass"
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

    var id: String { "\(action.rawValue)/\(owner)" }

    /// Reference copy shape: `Codex also uses ⌘⌘` / `Context for Claude and Codex both use ⌘⌘.`
    var title: String { "\(owner) also uses \(chord.displayString)" }

    var subtitle: String {
        "Context for Claude and \(owner) both use \(chord.displayString)."
    }
}

enum ShortcutRecordResult: Equatable, Sendable {
    case recorded
    /// The chord is reserved by the system (⌘Q, ⌘Tab) or already used by the other slot.
    case rejected(String)
}

// MARK: - The seam

/// What the General pane needs from the global-shortcut layer, and nothing else.
///
/// The shortcut layer (`Sources/ContextApp/Shortcuts/*`) is being built separately and did not exist
/// when this pane was written, so the pane depends on this protocol rather than on that layer. Three
/// things about the shape are load-bearing:
///
/// - **`binding(for:)` returns an optional.** Nil is *cleared*, which the reference copy makes a real
///   state ("Clear it to use ⌘⌘") rather than an error — a cleared slot falls back to
///   `ShortcutAction.defaultChord`, and the recorder shows that chord greyed.
/// - **`record` can refuse.** A recorder that always succeeds would let the user bind ⌘Q.
/// - **Conflicts are queried, never stored.** `I3` requires the row to appear *only* on a real
///   conflict, which means a live check against other installed tools every time the pane appears —
///   a persisted flag would leave the row on screen after the user uninstalled the other tool.
@MainActor
protocol ShortcutBindingProvider: AnyObject {
    /// The chord in force for `action`, or nil when the slot is cleared.
    func binding(for action: ShortcutAction) -> SettingsShortcutChord?
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

/// The stand-in until the real layer lands.
///
/// It registers **nothing** with the system, and says so: a stub that pretended to install a global
/// hotkey would make the pane look finished while `⌘⌘` did nothing, which is the failure mode `J7`
/// names. It does keep real state, so the recorder, the cleared state and the rejection path are all
/// exercised by the pane and by `SettingsTests` exactly as they will be against the real provider.
@MainActor
final class InMemoryShortcutBindings: ShortcutBindingProvider {

    /// Chords macOS will never hand an app, so a recorder that accepted them would produce a
    /// shortcut that silently never fires.
    static let reservedChords: [SettingsShortcutChord] = [
        SettingsShortcutChord(keyCode: 12, modifierFlags: .command),  // ⌘Q
        SettingsShortcutChord(keyCode: 48, modifierFlags: .command),  // ⌘Tab
        SettingsShortcutChord(keyCode: 49, modifierFlags: .command),  // ⌘Space
    ]

    private var chords: [ShortcutAction: SettingsShortcutChord]
    private var declaredConflicts: [SettingsShortcutConflict]
    private var observers: [UUID: @MainActor () -> Void] = [:]

    init(
        chords: [ShortcutAction: SettingsShortcutChord]? = nil,
        conflicts: [SettingsShortcutConflict] = []
    ) {
        self.chords =
            chords
            ?? Dictionary(uniqueKeysWithValues: ShortcutAction.allCases.map { ($0, $0.defaultChord) })
        self.declaredConflicts = conflicts
    }

    func binding(for action: ShortcutAction) -> SettingsShortcutChord? { chords[action] }

    func conflicts() -> [SettingsShortcutConflict] { declaredConflicts }

    func record(_ chord: SettingsShortcutChord, for action: ShortcutAction) -> ShortcutRecordResult {
        if Self.reservedChords.contains(chord) {
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
