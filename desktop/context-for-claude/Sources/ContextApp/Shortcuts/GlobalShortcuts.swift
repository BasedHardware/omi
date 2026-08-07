import AppKit
import Carbon.HIToolbox
import ContextCore
import Foundation

// MARK: - Modifiers

/// The four modifiers a chord can involve. `capsLock` and `fn` are deliberately absent: neither is
/// something a user thinks of as part of a shortcut, and both arrive in `flagsChanged` for reasons
/// that have nothing to do with the keys being pressed (a stuck Caps Lock, a Touch Bar mode change).
struct ShortcutModifiers: OptionSet, Hashable, Sendable {
    let rawValue: Int

    static let command = ShortcutModifiers(rawValue: 1 << 0)
    static let shift = ShortcutModifiers(rawValue: 1 << 1)
    static let option = ShortcutModifiers(rawValue: 1 << 2)
    static let control = ShortcutModifiers(rawValue: 1 << 3)

    /// Only the four that matter, so a Caps Lock or Fn change can never look like a chord change.
    init(_ flags: NSEvent.ModifierFlags) {
        var result: ShortcutModifiers = []
        if flags.contains(.command) { result.insert(.command) }
        if flags.contains(.shift) { result.insert(.shift) }
        if flags.contains(.option) { result.insert(.option) }
        if flags.contains(.control) { result.insert(.control) }
        self = result
    }

    init(rawValue: Int) { self.rawValue = rawValue }

    /// Apple's order: ⌃⌥⇧⌘, which is the order every macOS menu prints them in.
    var display: String {
        var out = ""
        if contains(.control) { out += "⌃" }
        if contains(.option) { out += "⌥" }
        if contains(.shift) { out += "⇧" }
        if contains(.command) { out += "⌘" }
        return out
    }

    var carbonFlags: UInt32 {
        var out: UInt32 = 0
        if contains(.command) { out |= UInt32(cmdKey) }
        if contains(.shift) { out |= UInt32(shiftKey) }
        if contains(.option) { out |= UInt32(optionKey) }
        if contains(.control) { out |= UInt32(controlKey) }
        return out
    }

    var appKitFlags: NSEvent.ModifierFlags {
        var out: NSEvent.ModifierFlags = []
        if contains(.command) { out.insert(.command) }
        if contains(.shift) { out.insert(.shift) }
        if contains(.option) { out.insert(.option) }
        if contains(.control) { out.insert(.control) }
        return out
    }
}

// MARK: - Chords

/// A shortcut, in a shape that can be compared against another product's binding.
///
/// Deliberately *not* a key code for the ordinary case. Comparing our binding to Codex's
/// `"CmdOrCtrl+Shift+K"` or Claude's `"double-tap-option"` has to happen on something both sides can
/// express, and a virtual key code is neither portable across layouts nor recoverable from an
/// accelerator string. The printed key label is.
enum ShortcutChord: Equatable, Hashable, Sendable {
    /// One modifier tapped twice, optionally with others held down throughout. `⌘⌘` is
    /// `.doubleTap(.command, alsoHeld: [])`; `⌘⌘⇧` is `.doubleTap(.command, alsoHeld: [.shift])`.
    ///
    /// Still here after `openTimeline` moved off it, for two reasons that are not going away:
    /// `openSearch` is still a double tap, and the conflict scanner has to be able to *say* what
    /// another tool bound — Claude's Quick Entry is ⌥⌥ and Codex spells one of its own bindings
    /// `doubleCommand`. A vocabulary that could not express a double tap could not report a
    /// collision with one.
    case doubleTap(ShortcutModifiers, alsoHeld: ShortcutModifiers)
    /// The two physical Command keys pressed together — left and right, at the same time, with
    /// nothing else held.
    ///
    /// Carries no `ShortcutModifiers` payload because it could not: `NSEvent.ModifierFlags` has one
    /// `.command` bit for two keys, so "both Command keys" is not a set this app's modifier
    /// vocabulary can spell. It is a separate gesture with separate rules (`BothCommandKeys`) and it
    /// prints separately — `⌘ + ⌘`, never `⌘⌘`, because `⌘⌘` is the *other* gesture and `openSearch`
    /// still uses it.
    case bothCommandKeys
    /// An ordinary key equivalent. `label` is upper-cased and layout-independent-ish: whatever the
    /// key prints without modifiers, or a name like `SPACE` for keys that print nothing.
    case key(label: String, modifiers: ShortcutModifiers)

    /// The one spelling of the both-Command gesture, and the one wording for it.
    ///
    /// Constants rather than literals in two files because `SettingsShortcutChord` prints the same
    /// gesture for the recorder: two spellings of one shortcut on two surfaces is a bug the user
    /// reads as "these are different shortcuts".
    static let bothCommandKeysDisplay = "⌘ + ⌘"
    static let bothCommandKeysPhrase = "both Command keys"

    var display: String {
        switch self {
        case .doubleTap(let tapped, let held):
            // The tapped modifier twice, then whatever is held — "⌘⌘⇧", which is how the reference
            // writes it.
            return tapped.display + tapped.display + held.display
        case .bothCommandKeys:
            // The `+` is doing real work. `⌘⌘` already means "tapped twice" everywhere else in this
            // app, so printing this gesture the same way would say the wrong thing about it — and
            // would print the timeline's chord identically to the first half of the search one.
            return Self.bothCommandKeysDisplay
        case .key(let label, let modifiers):
            return modifiers.display + label
        }
    }

    /// The chord said out loud, for copy that has to be understood rather than decoded — onboarding
    /// teaching the gesture, and any accessibility label.
    ///
    /// `display` is glyphs, and glyphs are exactly what fails here: `⌘ + ⌘` reads out as three
    /// symbols and none of the meaning, and a user who has never seen the gesture cannot tell it
    /// from `⌘⌘` by looking. Every case answers, so no surface has to special-case one gesture to
    /// get a sentence out of a chord.
    var spokenDescription: String {
        switch self {
        case .doubleTap(let tapped, let held):
            let tap = "a double tap of \(tapped.display)"
            return held.isEmpty ? tap : "\(tap) with \(held.display) held"
        case .bothCommandKeys:
            return Self.bothCommandKeysPhrase
        case .key(let label, let modifiers):
            // A key equivalent has no gesture to explain: it is held and struck like every other
            // shortcut on the machine, and its glyphs already say so.
            return modifiers.display + label
        }
    }
}

// MARK: - The tap detector

/// The double-tap rules, as a value.
///
/// Split out from the event plumbing on purpose: "two Command presses inside 380 ms with nothing in
/// between" is the whole feature, and it is the part that can be wrong in ways no amount of clicking
/// around would reveal. Feeding it synthetic snapshots is the only way to assert what happens when
/// someone types ⌘C twice quickly, or holds ⌘ for a second, or taps ⌘ then adds Shift.
///
/// Fires on the **second release**, not the second press. Firing on the press is a few tens of
/// milliseconds quicker and wrong: `⌘` down, `⌘` down again and *held* is the opening of ⌘S, and a
/// timeline window that opens on its way there is worse than one that opens 40 ms later.
struct ModifierDoubleTap {
    /// Between the two presses. The reference calls for 350–400 ms; 380 is the middle of that, and
    /// comfortably below the ~500 ms at which two deliberate taps stop feeling like one gesture.
    static let maxGap: TimeInterval = 0.380
    /// A press held longer than this is a hold, not a tap — holding ⌘ is how macOS shows menu
    /// shortcut hints, and it must never count.
    static let maxHold: TimeInterval = 0.400

    /// One `flagsChanged`, reduced to what the rules need. `at` is monotonic (`NSEvent.timestamp`).
    struct Snapshot: Equatable {
        let modifiers: ShortcutModifiers
        let at: TimeInterval

        init(modifiers: ShortcutModifiers, at: TimeInterval) {
            self.modifiers = modifiers
            self.at = at
        }
    }

    /// The modifier being watched for a double tap.
    private let tapped: ShortcutModifiers

    // The press currently in flight, if the modifier is down.
    private var pressBeganAt: TimeInterval?
    private var pressHeld: ShortcutModifiers = []
    private var pressIsClean = true

    // The last press that completed as a clean tap, and is still eligible to be the first half.
    private var firstTapBeganAt: TimeInterval?
    private var firstTapHeld: ShortcutModifiers = []

    private var wasDown = false

    init(tapped: ShortcutModifiers = .command) {
        self.tapped = tapped
    }

    /// - Returns: the modifiers held alongside the tapped one when a double tap completes, or `nil`.
    mutating func flagsChanged(_ snapshot: Snapshot) -> ShortcutModifiers? {
        let isDown = snapshot.modifiers.contains(tapped)
        let held = snapshot.modifiers.subtracting(tapped)
        defer { wasDown = isDown }

        if isDown, !wasDown {
            // Press.
            pressBeganAt = snapshot.at
            pressHeld = held
            pressIsClean = true
            return nil
        }

        if !isDown, wasDown {
            // Release.
            let began = pressBeganAt
            pressBeganAt = nil
            guard let began,
                pressIsClean,
                // A tap has to be short, and the modifiers held around it have to be the same at
                // both ends — ⌘ down, then Shift added, then ⌘ up is not a chord anyone is aiming at.
                snapshot.at - began <= Self.maxHold,
                held == pressHeld
            else {
                forgetHistory()
                return nil
            }

            if let firstBegan = firstTapBeganAt,
                firstTapHeld == held,
                began - firstBegan <= Self.maxGap {
                forgetHistory()
                return held
            }

            firstTapBeganAt = began
            firstTapHeld = held
            return nil
        }

        // A modifier changed while the tapped one was down (or while nothing was down). Changing the
        // held set mid-press is what disqualifies ⌘ → ⌘⇧ from reading as either chord.
        if isDown, held != pressHeld {
            pressIsClean = false
        }
        return nil
    }

    /// Any ordinary key going down. `⌘C ⌘C` typed quickly is two presses inside the window, and the
    /// only thing that tells it apart from `⌘⌘` is that a key happened in between.
    mutating func keyPressed() {
        pressIsClean = false
        forgetHistory()
    }

    /// Drops every bit of in-flight state. Called when monitoring restarts, because the modifier may
    /// have gone up while we were not watching and `wasDown` would then be a lie.
    mutating func reset() {
        pressBeganAt = nil
        pressHeld = []
        pressIsClean = true
        wasDown = false
        forgetHistory()
    }

    private mutating func forgetHistory() {
        firstTapBeganAt = nil
        firstTapHeld = []
    }
}

// MARK: - The both-Command detector

/// The "press both Command keys at once" rules, as a value.
///
/// Split from the event plumbing for the same reason `ModifierDoubleTap` is, and it matters more
/// here: there is no keyboard in a test process, so synthetic snapshots are the only proof that
/// holding one Command for a second and then reaching for the other does *not* open a window, and
/// that ⌘C typed with two thumbs down does not either.
///
/// ## Left and right, and how we can tell them apart
///
/// `NSEvent.ModifierFlags.command` is one bit for two keys. Holding the left Command and adding the
/// right changes nothing about a `ShortcutModifiers` — which is why this gesture cannot be built on
/// `ModifierDoubleTap.Snapshot`, and why `⌘ + ⌘` is not `⌘⌘` with better wording. Two ways to
/// recover the missing bit, and this takes the first:
///
/// 1. **`NSEvent.keyCode`.** A `flagsChanged` names the modifier key that moved: `kVK_Command` (55)
///    is the left one, `kVK_RightCommand` (54) the right. Named, public constants, out of a header
///    this file already imports.
/// 2. **The device-dependent flag bits.** `NX_DEVICELCMDKEYMASK` (0x8) and `NX_DEVICERCMDKEYMASK`
///    (0x10) sit in `event.modifierFlags.rawValue` below the bits AppKit publishes — and
///    `NSEvent.ModifierFlags.deviceIndependentFlagsMask` exists precisely to throw them away, which
///    is Apple naming which of the two surfaces is the supported one. They also arrive from IOKit's
///    `IOLLEvent.h` rather than from anything AppKit documents, and a synthetic or remapped event
///    can carry `.command` with neither device bit set.
///
/// (2) has one genuine advantage: every event carries the whole state, so it cannot drift, whereas
/// (1) has to *accumulate* which keys it believes are down and one missed event leaves that belief
/// wrong — and a global monitor really does miss events, because macOS stops delivering them while
/// a secure input field is focused. `maxOffset` is what makes that harmless rather than dangerous: a
/// stale "down" carries a stale timestamp, and a key that went down two seconds ago can no longer
/// pair with one going down now. So the failure mode of the supported surface is a gesture that does
/// not fire, and the user presses again.
///
/// ## Keyboards where this gesture does not exist
///
/// Every Mac laptop and every Apple keyboard has two Command keys. Plenty of third-party boards do
/// not, or report both of them as one key code, and a remapper (Karabiner, `hidutil`) can leave a
/// machine with one. On any of those this simply never fires — the second press either never arrives
/// or cancels the first through the toggle below — and nothing here guesses, because a guess would
/// be a window opening on a keystroke the user did not make. That failure is survivable only because
/// it is not the only door: the Settings recorder binds an ordinary key equivalent, which needs no
/// Accessibility grant at all, and the menu bar carries "Open Timeline" as a plain item.
struct BothCommandKeys {
    /// How far apart the two presses may be and still be one gesture.
    ///
    /// Two hands do not land on the same clock tick — an intentional two-key chord is tens of
    /// milliseconds apart, and one hand spanning both Command keys is slower again. 250 ms is
    /// generous about that while staying clear of `ModifierDoubleTap.maxHold` (400 ms), which is
    /// already this file's line between a tap and a hold: a Command *held* down while reading menu
    /// shortcut hints can never pair with the other one being pressed later, so the two gestures
    /// stay tellable apart on one keyboard.
    static let maxOffset: TimeInterval = 0.250

    /// 55 and 54. Named rather than spelled, and exposed so a test reads as the gesture rather than
    /// as two magic numbers.
    static let leftCommand = UInt16(kVK_Command)
    static let rightCommand = UInt16(kVK_RightCommand)

    /// One `flagsChanged`, reduced to what the rules need. `keyCode` is the modifier key that moved,
    /// which is the only thing in the event that tells the two Command keys apart; `at` is monotonic
    /// (`NSEvent.timestamp`).
    struct Snapshot: Equatable {
        let modifiers: ShortcutModifiers
        let keyCode: UInt16
        let at: TimeInterval
    }

    // When each Command key went down, as far as this can tell.
    private var leftDownAt: TimeInterval?
    private var rightDownAt: TimeInterval?

    /// Set when something turns the gesture in flight into a different one — another modifier, or an
    /// ordinary key. Sticky until every Command is back up, like `ModifierDoubleTap.pressIsClean`:
    /// Shift arriving and leaving again does not restore a gesture the user already made into
    /// something else.
    private var disqualified = false

    /// Set on the fire, cleared on release. This is the whole of "once per gesture".
    private var fired = false

    /// - Returns: true exactly once per gesture, on the press of the *second* Command key.
    mutating func flagsChanged(_ snapshot: Snapshot) -> Bool {
        guard snapshot.modifiers.contains(.command) else {
            // Every Command is up. The only thing that re-arms, which is what "re-arms only after
            // release" means — and the repair for any belief below that went stale while the monitor
            // was not being delivered events.
            reset()
            return false
        }

        let wasIdle = leftDownAt == nil && rightDownAt == nil
        // A Command key code arriving while the Command bit is still set is either that key going
        // down, or that key coming up while the other one is still holding the bit set. The event
        // does not say which — `flagsChanged` carries a state, not a direction — so this toggles.
        // The guard above is what stops a toggle that got out of step from outliving the keys.
        switch snapshot.keyCode {
        case Self.leftCommand:
            leftDownAt = leftDownAt == nil ? snapshot.at : nil
        case Self.rightCommand:
            rightDownAt = rightDownAt == nil ? snapshot.at : nil
        default:
            // Some other modifier moved (or Caps Lock did, which `ShortcutModifiers` has already
            // dropped). It cannot change which Command keys are down.
            break
        }

        if wasIdle, leftDownAt != nil || rightDownAt != nil {
            // The first Command of a fresh gesture. Whatever disqualified the last one is over —
            // without this, one ⌘C would poison every attempt until the next modifier release, and
            // the modifier release the user makes after ⌘C is the one that already happened.
            disqualified = false
            fired = false
        }

        // Anything else held makes this a different gesture. Consistent with `doubleTap`'s
        // `alsoHeld`, where the held set has to match the chord exactly: `.bothCommandKeys` carries
        // no held set at all, so the only set it matches is the empty one.
        if snapshot.modifiers != [.command] { disqualified = true }

        guard !fired, !disqualified,
            let left = leftDownAt, let right = rightDownAt,
            abs(left - right) <= Self.maxOffset
        else {
            return false
        }
        // Fires on the second *press*, where `ModifierDoubleTap` deliberately waits for the release.
        // The reason it waits does not apply here: ⌘ tapped and then held is the opening of ⌘S, so
        // firing early there would preempt a real shortcut — whereas macOS collapses the two Command
        // keys into one modifier, so no key equivalent anywhere on the machine can require both and
        // there is nothing this gesture can be the beginning of. Waiting for the release would only
        // make the window arrive however long the user rests on the keys.
        fired = true
        return true
    }

    /// Any ordinary key going down. Both Commands down with a letter struck between them is a ⌘-key
    /// shortcut typed with two thumbs, not this gesture.
    mutating func keyPressed() {
        disqualified = true
    }

    /// Drops every belief about which keys are down. Called when monitoring restarts, because both
    /// keys may have gone up while we were not watching.
    mutating func reset() {
        leftDownAt = nil
        rightDownAt = nil
        disqualified = false
        fired = false
    }
}

// MARK: - Global shortcuts

/// The two system-wide shortcuts, and the honest truth about whether they are armed.
///
/// Two mechanisms, because the two kinds of binding are not the same problem:
///
/// - **The gesture defaults** (`⌘ + ⌘`, `⌘⌘⇧`) cannot be registered as hot keys at all. Neither the
///   two Command keys pressed together nor a modifier tapped twice is a key equivalent, so
///   `RegisterEventHotKey` has nothing to take; the only route is watching `flagsChanged` across the
///   whole system, which macOS gates behind Accessibility. When that grant is missing the shortcut
///   does not fire, and `readiness(for:)` says so rather than letting Settings imply otherwise.
/// - **A recorded key equivalent** goes through `RegisterEventHotKey`, which needs no permission at
///   all. So a user who rebinds the shortcut gets one that works on a machine where Accessibility
///   was refused — and, just as importantly, the app stops observing every keystroke on the system
///   the moment it no longer needs to.
///
/// Nothing here consumes an event. The monitors are observers; a Carbon hot key is exclusive by
/// design, which is what makes conflict detection (`ShortcutConflicts`) worth doing at all.
@MainActor
final class GlobalShortcuts {
    static let shared = GlobalShortcuts()

    // MARK: Actions

    enum Action: String, CaseIterable, Sendable {
        case openTimeline
        case openSearch

        /// The Settings row title, verbatim from the reference's General pane.
        var title: String {
            switch self {
            case .openTimeline: return "Open Timeline Shortcut"
            case .openSearch: return "Open Search Shortcut"
            }
        }

        /// The reference's subtitle, with our own default spelled out — the copy is what tells the
        /// user that clearing the recorder is a real choice and not a broken state.
        var subtitle: String {
            "Record a keyboard shortcut. Clear it to use \(defaultChord.display)."
        }

        /// `⌘ + ⌘` for the timeline, `⌘⌘⇧` for search.
        ///
        /// The timeline used to be `⌘⌘` — a double tap — and it was reported as the wrong gesture
        /// twice: *"expressing both the command keys one by one. It's supposed to be both the
        /// command keys together"*, and then *"it should not be clicking the command key twice, it
        /// should be clicking both command keys on the keyboard together."* Two ⌘ glyphs side by
        /// side is a picture of the two keys a Mac actually has, so that is the gesture it was read
        /// as, and the app is now what it looks like.
        ///
        /// Search stays a double tap. Its chord is `⌘⌘⇧`, which cannot be confused with `⌘ + ⌘` by
        /// hand or by this file — the two detectors cannot both fire on one gesture, since pressing
        /// both Command keys puts the `.command` bit down once and a double tap puts it down twice.
        var defaultChord: ShortcutChord {
            switch self {
            case .openTimeline: return .bothCommandKeys
            case .openSearch: return .doubleTap(.command, alsoHeld: [.shift])
            }
        }

        /// Stable, small, and never zero — Carbon hot key ids are `UInt32` and 0 is a legal id we
        /// would not be able to tell from an uninitialised struct.
        fileprivate var hotKeyID: UInt32 {
            switch self {
            case .openTimeline: return 1
            case .openSearch: return 2
            }
        }

        /// Namespaced the way every other persisted value in this app is (see `Permissions.Key`).
        var storageKey: String {
            "context.shortcut.\(rawValue).keyEquivalent"
        }
    }

    /// A shortcut the user recorded. `label` is captured at record time from the event itself, so it
    /// is what that key prints on *their* layout rather than what it would print on a US one.
    struct Recorded: Equatable, Sendable {
        var keyCode: UInt16
        var modifiers: ShortcutModifiers
        var label: String

        var chord: ShortcutChord { .key(label: label, modifiers: modifiers) }
    }

    enum Binding: Equatable, Sendable {
        /// Nothing recorded, so the action answers to the modifier gesture it ships with —
        /// `⌘ + ⌘` or `⌘⌘⇧`, whichever `Action.defaultChord` names. Named for the *kind* of binding
        /// rather than for one gesture, because the timeline's default is no longer a double tap and
        /// a case called `doubleTapDefault` would have quietly become a lie about half of them.
        case gestureDefault
        case recorded(Recorded)
    }

    /// What Settings is allowed to claim.
    enum Readiness: Equatable, Sendable {
        /// Registered, and it will fire.
        case armed
        /// A gesture binding with no Accessibility grant. The shortcut does nothing; the row has
        /// to say that and offer the pane.
        case needsAccessibility
        /// Registration was refused — almost always because something else on the machine already
        /// owns this exact key equivalent.
        case rejected(String)
    }

    // MARK: Storage

    /// Where a recorded binding lives.
    ///
    /// Split out from the class so the persistence rules — above all "nothing stored means the
    /// gesture default", which is the whole of the reference's "Clear it to use ⌘ + ⌘" — can be
    /// asserted without registering a system-wide hot key from a test process.
    struct Store {
        let defaults: UserDefaults

        init(defaults: UserDefaults = .standard) {
            self.defaults = defaults
        }

        func binding(for action: Action) -> Binding {
            guard let stored = defaults.dictionary(forKey: action.storageKey),
                let keyCode = stored["keyCode"] as? Int,
                let modifiers = stored["modifiers"] as? Int,
                let label = stored["label"] as? String,
                !label.isEmpty
            else {
                return .gestureDefault
            }
            return .recorded(
                Recorded(
                    keyCode: UInt16(truncatingIfNeeded: keyCode),
                    modifiers: ShortcutModifiers(rawValue: modifiers),
                    label: label))
        }

        func chord(for action: Action) -> ShortcutChord {
            switch binding(for: action) {
            case .gestureDefault: return action.defaultChord
            case .recorded(let recorded): return recorded.chord
            }
        }

        /// `nil` clears the binding, which is exactly what the reference's copy promises.
        func setRecorded(_ recorded: Recorded?, for action: Action) {
            guard let recorded else {
                defaults.removeObject(forKey: action.storageKey)
                return
            }
            defaults.set(
                [
                    "keyCode": Int(recorded.keyCode),
                    "modifiers": recorded.modifiers.rawValue,
                    "label": recorded.label,
                ],
                forKey: action.storageKey)
        }
    }

    // MARK: State

    private let store: Store
    /// The two gesture recognizers, both fed every `flagsChanged`. Neither can steal the other's
    /// gesture: pressing both Command keys puts the `.command` bit down once, and a double tap puts
    /// it down twice, so there is no ordering between them to get wrong.
    private var doubleTap = ModifierDoubleTap(tapped: .command)
    private var bothCommands = BothCommandKeys()
    private var globalMonitor: Any?
    private var localMonitor: Any?
    private var hotKeys: [Action: EventHotKeyRef] = [:]
    private var rejections: [Action: String] = [:]
    private var onTrigger: ((Action) -> Void)?
    /// Extra listeners, for a surface that needs to know a chord really fired without taking the
    /// app's single handler away from it.
    ///
    /// The tutorial is why this exists: its timeline beat may only be satisfied by the user
    /// genuinely pressing the chord, and the window that opens is opened by the app's own handler —
    /// not by the tutorial reaching for `RewindWindow` itself. Replacing `onTrigger` for the length
    /// of a walkthrough would have meant the tutorial owning the shortcut, which is exactly the
    /// arrangement where "we opened something" can quietly stand in for "they pressed it".
    private var observers: [UUID: (Action) -> Void] = [:]
    private var carbonHandler: EventHandlerRef?
    private var activationObserver: NSObjectProtocol?

    init(store: Store = Store()) {
        self.store = store
    }

    // MARK: Bindings

    func binding(for action: Action) -> Binding { store.binding(for: action) }

    func chord(for action: Action) -> ShortcutChord { store.chord(for: action) }

    /// What the recorder shows. Never blank: a cleared binding shows the gesture default, because
    /// that is what will actually happen.
    func display(for action: Action) -> String { chord(for: action).display }

    func setRecorded(_ recorded: Recorded?, for action: Action) {
        store.setRecorded(recorded, for: action)
        rejections[action] = nil
        // Re-registering both is cheaper than reasoning about which half moved, and it is the only
        // way a newly cleared binding gets the monitor back.
        reapply()
    }

    /// The chords that are live right now, for `ShortcutConflicts`. Only bindings that are actually
    /// armed appear: a chord we failed to register is not a chord anyone else can conflict with.
    func armedChords() -> [Action: ShortcutChord] {
        var out: [Action: ShortcutChord] = [:]
        for action in Action.allCases where readiness(for: action) == .armed {
            out[action] = chord(for: action)
        }
        return out
    }

    // MARK: Readiness

    func readiness(for action: Action) -> Readiness {
        if let reason = rejections[action] { return .rejected(reason) }
        switch binding(for: action) {
        case .gestureDefault:
            return AXElement.isTrusted ? .armed : .needsAccessibility
        case .recorded:
            return hotKeys[action] != nil ? .armed : .rejected("macOS refused this shortcut.")
        }
    }

    /// True when any binding still needs Accessibility. The one thing Settings needs for a summary
    /// line, without asking about each row.
    var needsAccessibility: Bool {
        Action.allCases.contains { readiness(for: $0) == .needsAccessibility }
    }

    // MARK: Lifecycle

    /// Registers everything and starts delivering. Idempotent.
    func start(onTrigger: @escaping (Action) -> Void) {
        self.onTrigger = onTrigger
        observeActivation()
        reapply()
    }

    /// Adds a listener that is told about every chord that fires, alongside the app's own handler.
    ///
    /// - Returns: a token to hand back to `removeObserver`. Observers are additive and never replace
    ///   `onTrigger`, so whatever the shortcut normally does still happens.
    @discardableResult
    func addObserver(_ observe: @escaping (Action) -> Void) -> UUID {
        let token = UUID()
        observers[token] = observe
        return token
    }

    func removeObserver(_ token: UUID) {
        observers[token] = nil
    }

    /// Re-evaluates permission and re-registers. Accessibility can be granted while the app runs and
    /// macOS posts nothing when it happens, so this is what Settings calls when it appears — and
    /// what the activation observer calls when the user comes back from the Accessibility pane.
    func refresh() {
        reapply()
    }

    func stop() {
        removeMonitors()
        for (_, ref) in hotKeys { UnregisterEventHotKey(ref) }
        hotKeys = [:]
        if let carbonHandler {
            RemoveEventHandler(carbonHandler)
            self.carbonHandler = nil
        }
        if let activationObserver {
            NotificationCenter.default.removeObserver(activationObserver)
            self.activationObserver = nil
        }
    }

    // MARK: Registration

    private func reapply() {
        // Hot keys first: a rejection there is what the monitor decision below must not paper over.
        for (_, ref) in hotKeys { UnregisterEventHotKey(ref) }
        hotKeys = [:]

        var wantsMonitor = false
        for action in Action.allCases {
            switch binding(for: action) {
            case .gestureDefault:
                wantsMonitor = true
            case .recorded(let recorded):
                register(recorded, for: action)
            }
        }

        if wantsMonitor, AXElement.isTrusted {
            installMonitors()
        } else {
            removeMonitors()
        }
    }

    private func register(_ recorded: Recorded, for action: Action) {
        installCarbonHandlerIfNeeded()
        var ref: EventHotKeyRef?
        let id = EventHotKeyID(signature: Self.signature, id: action.hotKeyID)
        let status = RegisterEventHotKey(
            UInt32(recorded.keyCode), recorded.modifiers.carbonFlags, id, GetApplicationEventTarget(), 0, &ref)
        if status == noErr, let ref {
            hotKeys[action] = ref
            rejections[action] = nil
            ContextLog.info("Registered \(action.rawValue) as \(recorded.chord.display)", Self.logCategory)
        } else {
            // The overwhelmingly likely cause is that something else on the machine already holds
            // this exact chord. Saying so is more useful than an OSStatus.
            rejections[action] = "Something else on this Mac already uses \(recorded.chord.display)."
            ContextLog.error(
                "Could not register \(action.rawValue) as \(recorded.chord.display) (OSStatus \(status))",
                Self.logCategory)
        }
    }

    private func installMonitors() {
        guard globalMonitor == nil, localMonitor == nil else { return }
        resetDetectors()

        // Passive: a global monitor cannot alter or swallow an event, which is the property that
        // keeps ⌘ behaving like ⌘ in every other app on the machine.
        globalMonitor = NSEvent.addGlobalMonitorForEvents(matching: [.flagsChanged, .keyDown]) { event in
            MainActor.assumeIsolated { GlobalShortcuts.shared.observe(event) }
        }
        // A global monitor never sees events delivered to our own process, so without this the
        // shortcut would die the moment one of our own windows had focus — including the search bar
        // it opens.
        localMonitor = NSEvent.addLocalMonitorForEvents(matching: [.flagsChanged, .keyDown]) { event in
            MainActor.assumeIsolated { GlobalShortcuts.shared.observe(event) }
            return event
        }
        ContextLog.info("Watching flagsChanged for the gesture defaults", Self.logCategory)
    }

    private func removeMonitors() {
        if let globalMonitor { NSEvent.removeMonitor(globalMonitor) }
        if let localMonitor { NSEvent.removeMonitor(localMonitor) }
        globalMonitor = nil
        localMonitor = nil
        resetDetectors()
    }

    /// Both, always together: a detector left holding a belief from before the gap is a detector
    /// that can fire on the first keypress after it.
    private func resetDetectors() {
        doubleTap.reset()
        bothCommands.reset()
    }

    /// Accessibility is granted in System Settings, and the only reliable signal that it happened is
    /// the user coming back to us.
    private func observeActivation() {
        guard activationObserver == nil else { return }
        activationObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.didBecomeActiveNotification, object: nil, queue: .main
        ) { _ in
            MainActor.assumeIsolated { GlobalShortcuts.shared.refresh() }
        }
    }

    // MARK: Delivery

    fileprivate func observe(_ event: NSEvent) {
        switch event.type {
        case .flagsChanged:
            let modifiers = ShortcutModifiers(event.modifierFlags)
            if let held = doubleTap.flagsChanged(.init(modifiers: modifiers, at: event.timestamp)) {
                fire(.doubleTap(.command, alsoHeld: held))
            }
            // `event.keyCode` is the modifier key that moved — 55 or 54 for the two Command keys —
            // and it is the only thing here that distinguishes them, since `modifiers` says
            // `.command` for either. Valid on `flagsChanged`, which is a keyboard event.
            if bothCommands.flagsChanged(
                .init(modifiers: modifiers, keyCode: event.keyCode, at: event.timestamp))
            {
                fire(.bothCommandKeys)
            }
        case .keyDown:
            doubleTap.keyPressed()
            bothCommands.keyPressed()
        default:
            break
        }
    }

    /// Delivers a gesture to whichever action is still on its default *and* ships that gesture.
    ///
    /// Only an action still on its default answers to a gesture: rebinding the timeline to ⌥Space
    /// and leaving search on ⌘⌘⇧ must not leave ⌘ + ⌘ opening the timeline as well. Matched against
    /// `defaultChord` itself rather than against a second copy of the gesture's parts, so the table
    /// Settings prints and the table that fires cannot drift apart.
    private func fire(_ chord: ShortcutChord) {
        guard
            let action = Action.allCases.first(where: {
                binding(for: $0) == .gestureDefault && $0.defaultChord == chord
            })
        else { return }
        deliver(action)
    }

    fileprivate func hotKeyFired(id: UInt32) {
        guard let action = Action.allCases.first(where: { $0.hotKeyID == id }) else { return }
        deliver(action)
    }

    private func deliver(_ action: Action) {
        ContextLog.info("\(action.rawValue) fired via \(chord(for: action).display)", Self.logCategory)
        // The app's handler first, observers second, and that order is load-bearing: the handler is
        // what opens the window, so an observer asking "is it up?" is asking after it has happened.
        onTrigger?(action)
        for observe in observers.values { observe(action) }
    }

    // MARK: Carbon plumbing

    private static let logCategory = "shortcuts"
    /// `'CtxS'`. Carbon signatures are four-char codes and the value only has to be ours.
    private static let signature: OSType = 0x4374_7853

    private func installCarbonHandlerIfNeeded() {
        guard carbonHandler == nil else { return }
        var spec = EventTypeSpec(
            eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        var ref: EventHandlerRef?
        // The handler is a C function pointer, so it cannot capture — it reads the id out of the
        // event and hands it to the singleton on the main actor.
        let status = InstallEventHandler(
            GetApplicationEventTarget(),
            { _, event, _ -> OSStatus in
                guard let event else { return OSStatus(eventNotHandledErr) }
                var id = EventHotKeyID()
                let read = GetEventParameter(
                    event,
                    EventParamName(kEventParamDirectObject),
                    EventParamType(typeEventHotKeyID),
                    nil,
                    MemoryLayout<EventHotKeyID>.size,
                    nil,
                    &id)
                guard read == noErr, id.signature == GlobalShortcuts.signature else {
                    return OSStatus(eventNotHandledErr)
                }
                let hotKeyID = id.id
                DispatchQueue.main.async {
                    MainActor.assumeIsolated { GlobalShortcuts.shared.hotKeyFired(id: hotKeyID) }
                }
                return noErr
            },
            1,
            &spec,
            nil,
            &ref)
        if status == noErr {
            carbonHandler = ref
        } else {
            ContextLog.error("Could not install the hot key handler (OSStatus \(status))", Self.logCategory)
        }
    }
}

// MARK: - Recording

extension GlobalShortcuts.Recorded {
    /// Builds a binding out of the event a recorder captured, or `nil` when the press is not a
    /// shortcut anyone can use.
    ///
    /// Rejected on purpose:
    /// - **A bare key.** `T` as a system-wide shortcut would eat the letter T everywhere.
    /// - **Shift alone.** `⇧T` is `T`, so it eats a letter too.
    /// - **Escape and Return.** Both mean something specific in every app on the machine.
    static func from(_ event: NSEvent) -> GlobalShortcuts.Recorded? {
        guard event.type == .keyDown else { return nil }
        let modifiers = ShortcutModifiers(event.modifierFlags)
        guard !modifiers.subtracting(.shift).isEmpty else { return nil }
        guard !unrecordableKeyCodes.contains(event.keyCode) else { return nil }
        return GlobalShortcuts.Recorded(
            keyCode: event.keyCode, modifiers: modifiers, label: label(for: event))
    }

    /// Escape and Return mean something specific in every app on the machine, so no modifier makes
    /// them free to take. Named here rather than inlined because the Settings recorder reaches this
    /// layer with a bare key code and has to refuse exactly the same keys — two lists would drift
    /// into a chord one path accepts and the other cannot register.
    static let unrecordableKeyCodes: Set<UInt16> = [
        UInt16(kVK_Escape), UInt16(kVK_Return), UInt16(kVK_ANSI_KeypadEnter),
    ]

    /// What the key prints, upper-cased, or a name for the keys that print nothing legible.
    ///
    /// The event is the better source than the key code: `charactersIgnoringModifiers` is what *this*
    /// keypress produced on this layout, with no lookup to get wrong. `ShortcutKeyLabel` is the same
    /// answer for callers who only hold a code.
    private static func label(for event: NSEvent) -> String {
        if let named = ShortcutKeyLabel.namedKeys[event.keyCode] { return named }
        let characters = event.charactersIgnoringModifiers ?? ""
        let trimmed = characters.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return ShortcutKeyLabel.label(for: event.keyCode) }
        return trimmed.uppercased()
    }
}
